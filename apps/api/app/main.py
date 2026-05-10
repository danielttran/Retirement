from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from planner_engine.common import AccountYearState, RothConversionLotState
from planner_engine.common import Person as EnginePerson
from planner_engine.projection import (
    AssumptionSet as EngineAssumptionSet,
)
from planner_engine.projection import (
    ExpenseStream as EngineExpenseStream,
)
from planner_engine.projection import (
    IncomeStream as EngineIncomeStream,
)
from planner_engine.projection import (
    ScenarioInput,
    SeppProjectionPlan,
    run_projection,
)
from planner_engine.roth import RothConversionPlan as EngineRothConversionPlan
from planner_engine.sepp.calculator import SeppCalculationInput
from planner_engine.sepp.calculator import calculate_initial_payment as _compute_sepp_payment
from planner_engine.withdrawal import DEFAULT_WITHDRAWAL_ORDER
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.database import DATABASE_PATH, get_session, init_db
from app.models import (
    Account,
    AssumptionSet,
    ExpenseStream,
    Household,
    IncomeStream,
    Person,
    ProjectionAccountBalance,
    ProjectionRunMetadata,
    ProjectionWarning,
    ProjectionYear,
    RothBasis,
    RothConversionPlan,
    Scenario,
    SeppPlan,
    WithdrawalStrategy,
)
from app.schemas import (
    AccountCreate,
    AccountRead,
    AssumptionSetRead,
    AssumptionSetUpdate,
    ExpenseStreamCreate,
    ExpenseStreamRead,
    HouseholdCreate,
    HouseholdRead,
    IncomeStreamCreate,
    IncomeStreamRead,
    ProjectionAccountBalanceRead,
    ProjectionRead,
    ProjectionRunMetadataRead,
    ProjectionWarningRead,
    ProjectionYearRead,
    RothConversionPlanCreate,
    RothConversionPlanRead,
    ScenarioDetail,
    ScenarioRead,
    SeppPlanCreate,
    SeppPlanRead,
    WithdrawalStrategyRead,
    WithdrawalStrategyUpdate,
)

SessionDep = Annotated[Session, Depends(get_session)]


def new_id() -> str:
    return str(uuid4())


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_year(value: str) -> int:
    return date.fromisoformat(value).year


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield

app = FastAPI(
    title="Personal Retirement Planner API",
    version="0.1.0",
    description="Local-first retirement projection API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system/database", tags=["system"])
def database_info() -> dict[str, str]:
    return {"path": str(DATABASE_PATH)}


@app.get("/households", response_model=list[HouseholdRead], tags=["households"])
def list_households(session: SessionDep) -> list[Household]:
    return list(
        session.scalars(select(Household).options(selectinload(Household.people))).all()
    )


@app.post(
    "/households",
    response_model=ScenarioDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["households"],
)
def create_household(
    payload: HouseholdCreate, session: SessionDep
) -> ScenarioDetail:
    household = Household(
        id=new_id(),
        name=payload.name,
        filing_status=payload.filing_status,
        state=payload.state,
        created_at=now_iso(),
    )
    person = Person(
        id=new_id(),
        household_id=household.id,
        name=payload.primary_person.name,
        dob=payload.primary_person.dob,
        retirement_date=payload.primary_person.retirement_date,
        life_expectancy_age=payload.primary_person.life_expectancy_age,
        is_primary=True,
    )
    scenario = Scenario(
        id=new_id(),
        household_id=household.id,
        name=payload.scenario_name,
        created_at=now_iso(),
    )
    assumptions = AssumptionSet(
        id=new_id(),
        scenario_id=scenario.id,
        engine_version="0.1.0",
        state=payload.state,
    )
    withdrawal_strategy = WithdrawalStrategy(
        id=new_id(),
        scenario_id=scenario.id,
        order_json=json.dumps(DEFAULT_WITHDRAWAL_ORDER),
    )
    session.add_all([household, person, scenario, assumptions, withdrawal_strategy])
    session.commit()
    return get_scenario(scenario.id, session)


@app.delete(
    "/households/{household_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["households"],
)
def delete_household(household_id: str, session: SessionDep) -> Response:
    household = session.get(Household, household_id)
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    scenario_ids = list(
        session.scalars(select(Scenario.id).where(Scenario.household_id == household_id))
    )
    for sid in scenario_ids:
        clear_projection_output(sid, session)
    session.delete(household)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/scenarios", response_model=list[ScenarioRead], tags=["scenarios"])
def list_scenarios(session: SessionDep) -> list[Scenario]:
    return list(session.scalars(select(Scenario).order_by(Scenario.created_at.desc())).all())


@app.get("/scenarios/{scenario_id}", response_model=ScenarioDetail, tags=["scenarios"])
def get_scenario(scenario_id: str, session: SessionDep) -> ScenarioDetail:
    scenario = session.scalar(
        select(Scenario)
        .where(Scenario.id == scenario_id)
        .options(selectinload(Scenario.household).selectinload(Household.people))
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    accounts = list(
        session.scalars(select(Account).where(Account.household_id == scenario.household_id)).all()
    )
    total = sum((account.current_balance for account in accounts), Decimal("0"))
    return ScenarioDetail(
        id=scenario.id,
        household_id=scenario.household_id,
        name=scenario.name,
        parent_scenario_id=scenario.parent_scenario_id,
        created_at=scenario.created_at,
        household=HouseholdRead.model_validate(scenario.household),
        accounts=[AccountRead.model_validate(account) for account in accounts],
        total_account_balance=total,
    )


@app.delete(
    "/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["scenarios"],
)
def delete_scenario(scenario_id: str, session: SessionDep) -> Response:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    clear_projection_output(scenario_id, session)
    session.delete(scenario)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/scenarios/{scenario_id}/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    tags=["accounts"],
)
def create_account(
    scenario_id: str, payload: AccountCreate, session: SessionDep
) -> Account:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    owner = session.get(Person, payload.owner_person_id)
    if owner is None or owner.household_id != scenario.household_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account owner")

    if payload.account_type == "taxable_brokerage" and payload.cost_basis_pct is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Taxable brokerage accounts require cost_basis_pct",
        )
    if payload.account_type in {"roth_ira", "roth_401k"} and (
        payload.roth_first_contribution_year is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Roth accounts require roth_first_contribution_year",
        )

    account = Account(
        id=new_id(),
        household_id=scenario.household_id,
        owner_person_id=payload.owner_person_id,
        name=payload.name,
        account_type=payload.account_type,
        current_balance=payload.current_balance,
        expected_return=payload.expected_return,
        return_stddev=payload.return_stddev,
        cost_basis_pct=payload.cost_basis_pct,
        roth_first_contribution_year=payload.roth_first_contribution_year,
        is_governmental_457b=payload.is_governmental_457b,
        has_rollover_basis_from_penalty_account=payload.has_rollover_basis_from_penalty_account,
        rollover_basis_pct=payload.rollover_basis_pct,
        hsa_qualified_medical_expense_pct=payload.hsa_qualified_medical_expense_pct,
        created_at=now_iso(),
    )
    session.add(account)
    if payload.account_type in {"roth_ira", "roth_401k"}:
        session.add(
            RothBasis(
                account_id=account.id,
                contributions_basis=payload.current_balance,
                conversions_basis=Decimal("0"),
                earnings_balance=Decimal("0"),
            )
        )
    session.commit()
    session.refresh(account)
    return account


@app.get(
    "/scenarios/{scenario_id}/accounts",
    response_model=list[AccountRead],
    tags=["accounts"],
)
def list_accounts(scenario_id: str, session: SessionDep) -> list[Account]:
    scenario = require_scenario(scenario_id, session)
    return list(
        session.scalars(select(Account).where(Account.household_id == scenario.household_id)).all()
    )


@app.put(
    "/scenarios/{scenario_id}/accounts/{account_id}",
    response_model=AccountRead,
    tags=["accounts"],
)
def update_account(
    scenario_id: str,
    account_id: str,
    payload: AccountCreate,
    session: SessionDep,
) -> Account:
    scenario = require_scenario(scenario_id, session)
    account = require_household_account(account_id, scenario.household_id, session)
    owner = session.get(Person, payload.owner_person_id)
    if owner is None or owner.household_id != scenario.household_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account owner")
    for key, value in payload.model_dump().items():
        setattr(account, key, value)
    session.commit()
    session.refresh(account)
    return account


@app.delete(
    "/scenarios/{scenario_id}/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["accounts"],
)
def delete_account(
    scenario_id: str, account_id: str, session: SessionDep
) -> Response:
    scenario = session.get(Scenario, scenario_id)
    account = session.get(Account, account_id)
    if scenario is None or account is None or account.household_id != scenario.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    session.delete(account)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/scenarios/{scenario_id}/income-streams",
    response_model=list[IncomeStreamRead],
    tags=["income"],
)
def list_income_streams(scenario_id: str, session: SessionDep) -> list[IncomeStream]:
    scenario = require_scenario(scenario_id, session)
    return list(
        session.scalars(
            select(IncomeStream).where(IncomeStream.household_id == scenario.household_id)
        ).all()
    )


@app.post(
    "/scenarios/{scenario_id}/income-streams",
    response_model=IncomeStreamRead,
    status_code=status.HTTP_201_CREATED,
    tags=["income"],
)
def create_income_stream(
    scenario_id: str,
    payload: IncomeStreamCreate,
    session: SessionDep,
) -> IncomeStream:
    scenario = require_scenario(scenario_id, session)
    if payload.person_id is not None:
        person = session.get(Person, payload.person_id)
        if person is None or person.household_id != scenario.household_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid person")
    stream = IncomeStream(id=new_id(), household_id=scenario.household_id, **payload.model_dump())
    session.add(stream)
    session.commit()
    session.refresh(stream)
    return stream


@app.put(
    "/scenarios/{scenario_id}/income-streams/{stream_id}",
    response_model=IncomeStreamRead,
    tags=["income"],
)
def update_income_stream(
    scenario_id: str,
    stream_id: str,
    payload: IncomeStreamCreate,
    session: SessionDep,
) -> IncomeStream:
    scenario = require_scenario(scenario_id, session)
    stream = require_income_stream(stream_id, scenario.household_id, session)
    for key, value in payload.model_dump().items():
        setattr(stream, key, value)
    session.commit()
    session.refresh(stream)
    return stream


@app.delete(
    "/scenarios/{scenario_id}/income-streams/{stream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["income"],
)
def delete_income_stream(scenario_id: str, stream_id: str, session: SessionDep) -> Response:
    scenario = require_scenario(scenario_id, session)
    stream = require_income_stream(stream_id, scenario.household_id, session)
    session.delete(stream)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/scenarios/{scenario_id}/expense-streams",
    response_model=list[ExpenseStreamRead],
    tags=["expenses"],
)
def list_expense_streams(scenario_id: str, session: SessionDep) -> list[ExpenseStream]:
    scenario = require_scenario(scenario_id, session)
    return list(
        session.scalars(
            select(ExpenseStream).where(ExpenseStream.household_id == scenario.household_id)
        ).all()
    )


@app.post(
    "/scenarios/{scenario_id}/expense-streams",
    response_model=ExpenseStreamRead,
    status_code=status.HTTP_201_CREATED,
    tags=["expenses"],
)
def create_expense_stream(
    scenario_id: str,
    payload: ExpenseStreamCreate,
    session: SessionDep,
) -> ExpenseStream:
    scenario = require_scenario(scenario_id, session)
    stream = ExpenseStream(id=new_id(), household_id=scenario.household_id, **payload.model_dump())
    session.add(stream)
    session.commit()
    session.refresh(stream)
    return stream


@app.put(
    "/scenarios/{scenario_id}/expense-streams/{stream_id}",
    response_model=ExpenseStreamRead,
    tags=["expenses"],
)
def update_expense_stream(
    scenario_id: str,
    stream_id: str,
    payload: ExpenseStreamCreate,
    session: SessionDep,
) -> ExpenseStream:
    scenario = require_scenario(scenario_id, session)
    stream = require_expense_stream(stream_id, scenario.household_id, session)
    for key, value in payload.model_dump().items():
        setattr(stream, key, value)
    session.commit()
    session.refresh(stream)
    return stream


@app.delete(
    "/scenarios/{scenario_id}/expense-streams/{stream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["expenses"],
)
def delete_expense_stream(scenario_id: str, stream_id: str, session: SessionDep) -> Response:
    scenario = require_scenario(scenario_id, session)
    stream = require_expense_stream(stream_id, scenario.household_id, session)
    session.delete(stream)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/scenarios/{scenario_id}/assumptions",
    response_model=AssumptionSetRead,
    tags=["assumptions"],
)
def get_assumptions(scenario_id: str, session: SessionDep) -> AssumptionSet:
    scenario = require_scenario(scenario_id, session)
    return get_or_create_assumptions(scenario, session)


@app.put(
    "/scenarios/{scenario_id}/assumptions",
    response_model=AssumptionSetRead,
    tags=["assumptions"],
)
def update_assumptions(
    scenario_id: str,
    payload: AssumptionSetUpdate,
    session: SessionDep,
) -> AssumptionSet:
    scenario = require_scenario(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    for key, value in payload.model_dump().items():
        setattr(assumptions, key, value)
    session.commit()
    session.refresh(assumptions)
    return assumptions


@app.get(
    "/scenarios/{scenario_id}/withdrawal-strategy",
    response_model=WithdrawalStrategyRead,
    tags=["withdrawal"],
)
def get_withdrawal_strategy(scenario_id: str, session: SessionDep) -> WithdrawalStrategy:
    scenario = require_scenario(scenario_id, session)
    return get_or_create_withdrawal_strategy(scenario, session)


@app.put(
    "/scenarios/{scenario_id}/withdrawal-strategy",
    response_model=WithdrawalStrategyRead,
    tags=["withdrawal"],
)
def update_withdrawal_strategy(
    scenario_id: str,
    payload: WithdrawalStrategyUpdate,
    session: SessionDep,
) -> WithdrawalStrategy:
    scenario = require_scenario(scenario_id, session)
    strategy = get_or_create_withdrawal_strategy(scenario, session)
    strategy.order_json = payload.order_json
    strategy.surplus_target = payload.surplus_target
    session.commit()
    session.refresh(strategy)
    return strategy


@app.get(
    "/scenarios/{scenario_id}/sepp-plans",
    response_model=list[SeppPlanRead],
    tags=["sepp"],
)
def list_sepp_plans(scenario_id: str, session: SessionDep) -> list[SeppPlan]:
    return list(
        session.scalars(select(SeppPlan).where(SeppPlan.scenario_id == scenario_id)).all()
    )


@app.post(
    "/scenarios/{scenario_id}/sepp-plans",
    response_model=SeppPlanRead,
    status_code=status.HTTP_201_CREATED,
    tags=["sepp"],
)
def create_sepp_plan(
    scenario_id: str,
    payload: SeppPlanCreate,
    session: SessionDep,
) -> SeppPlan:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.account_id, scenario.household_id, session)
    plan = SeppPlan(id=new_id(), scenario_id=scenario.id, **payload.model_dump())
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


@app.put(
    "/scenarios/{scenario_id}/sepp-plans/{plan_id}",
    response_model=SeppPlanRead,
    tags=["sepp"],
)
def update_sepp_plan(
    scenario_id: str,
    plan_id: str,
    payload: SeppPlanCreate,
    session: SessionDep,
) -> SeppPlan:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.account_id, scenario.household_id, session)
    plan = session.get(SeppPlan, plan_id)
    if plan is None or plan.scenario_id != scenario_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SEPP plan not found")
    for key, value in payload.model_dump().items():
        setattr(plan, key, value)
    session.commit()
    session.refresh(plan)
    return plan


@app.delete(
    "/scenarios/{scenario_id}/sepp-plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["sepp"],
)
def delete_sepp_plan(scenario_id: str, plan_id: str, session: SessionDep) -> Response:
    require_scenario(scenario_id, session)
    plan = session.get(SeppPlan, plan_id)
    if plan is None or plan.scenario_id != scenario_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SEPP plan not found")
    session.delete(plan)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/scenarios/{scenario_id}/roth-conversions",
    response_model=list[RothConversionPlanRead],
    tags=["roth"],
)
def list_roth_conversions(scenario_id: str, session: SessionDep) -> list[RothConversionPlan]:
    return list(
        session.scalars(
            select(RothConversionPlan).where(RothConversionPlan.scenario_id == scenario_id)
        ).all()
    )


@app.post(
    "/scenarios/{scenario_id}/roth-conversions",
    response_model=RothConversionPlanRead,
    status_code=status.HTTP_201_CREATED,
    tags=["roth"],
)
def create_roth_conversion(
    scenario_id: str,
    payload: RothConversionPlanCreate,
    session: SessionDep,
) -> RothConversionPlan:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.source_account_id, scenario.household_id, session)
    require_household_account(payload.destination_account_id, scenario.household_id, session)
    if payload.tax_payment_source_account_id is not None:
        require_household_account(
            payload.tax_payment_source_account_id,
            scenario.household_id,
            session,
        )
    plan = RothConversionPlan(id=new_id(), scenario_id=scenario.id, **payload.model_dump())
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


@app.put(
    "/scenarios/{scenario_id}/roth-conversions/{plan_id}",
    response_model=RothConversionPlanRead,
    tags=["roth"],
)
def update_roth_conversion(
    scenario_id: str,
    plan_id: str,
    payload: RothConversionPlanCreate,
    session: SessionDep,
) -> RothConversionPlan:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.source_account_id, scenario.household_id, session)
    require_household_account(payload.destination_account_id, scenario.household_id, session)
    if payload.tax_payment_source_account_id is not None:
        require_household_account(
            payload.tax_payment_source_account_id,
            scenario.household_id,
            session,
        )
    plan = session.get(RothConversionPlan, plan_id)
    if plan is None or plan.scenario_id != scenario_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roth conversion plan not found",
        )
    for key, value in payload.model_dump().items():
        setattr(plan, key, value)
    session.commit()
    session.refresh(plan)
    return plan


@app.delete(
    "/scenarios/{scenario_id}/roth-conversions/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["roth"],
)
def delete_roth_conversion(scenario_id: str, plan_id: str, session: SessionDep) -> Response:
    require_scenario(scenario_id, session)
    plan = session.get(RothConversionPlan, plan_id)
    if plan is None or plan.scenario_id != scenario_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Roth conversion plan not found",
        )
    session.delete(plan)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/scenarios/{scenario_id}/run-projection",
    response_model=ProjectionRead,
    tags=["projection"],
)
def run_scenario_projection(scenario_id: str, session: SessionDep) -> ProjectionRead:
    scenario = load_scenario_for_projection(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    projection_input = build_projection_input(scenario, assumptions, session)
    run = run_projection(projection_input, assumptions.irs_data_version, assumptions.engine_version)

    clear_projection_output(scenario.id, session)
    metadata = ProjectionRunMetadata(
        id=run.metadata.id,
        scenario_id=scenario.id,
        run_at=run.metadata.run_at,
        engine_version=run.metadata.engine_version,
        irs_data_version=run.metadata.irs_data_version,
        assumption_snapshot_json=json.dumps(run.metadata.assumption_snapshot),
        convergence_log_json=json.dumps(run.metadata.convergence_log),
    )
    session.add(metadata)
    session.add_all(
        ProjectionYear(
            id=row.id,
            scenario_id=row.scenario_id,
            year=row.year,
            age_primary=row.age_primary,
            age_spouse=row.age_spouse,
            gross_income=row.gross_income,
            required_distributions=row.required_distributions,
            flexible_withdrawals=row.flexible_withdrawals,
            roth_conversions=row.roth_conversions,
            expenses=row.expenses,
            federal_tax=row.federal_tax,
            state_tax=row.state_tax,
            early_withdrawal_penalty=row.early_withdrawal_penalty,
            magi=row.magi,
            provisional_income=row.provisional_income,
            ss_taxable_portion=row.ss_taxable_portion,
            surplus=row.surplus,
            ending_net_worth=row.ending_net_worth,
        )
        for row in run.years
    )
    session.add_all(
        ProjectionAccountBalance(
            id=row.id,
            scenario_id=row.scenario_id,
            year=row.year,
            account_id=row.account_id,
            beginning_balance=row.beginning_balance,
            contributions=row.contributions,
            distributions=row.distributions,
            investment_return=row.investment_return,
            ending_balance=row.ending_balance,
        )
        for row in run.account_balances
    )
    session.add_all(
        ProjectionWarning(
            id=warning.id,
            scenario_id=warning.scenario_id,
            year=warning.year,
            severity=warning.severity,
            code=warning.code,
            message=warning.message,
        )
        for warning in run.warnings
    )
    session.commit()
    return get_projection(scenario_id, session)


@app.get(
    "/scenarios/{scenario_id}/projection",
    response_model=ProjectionRead,
    tags=["projection"],
)
def get_projection(scenario_id: str, session: SessionDep) -> ProjectionRead:
    metadata = session.scalar(
        select(ProjectionRunMetadata)
        .where(ProjectionRunMetadata.scenario_id == scenario_id)
        .order_by(ProjectionRunMetadata.run_at.desc())
    )
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projection not found")
    years = list(
        session.scalars(
            select(ProjectionYear)
            .where(ProjectionYear.scenario_id == scenario_id)
            .order_by(ProjectionYear.year)
        ).all()
    )
    balances = list(
        session.scalars(
            select(ProjectionAccountBalance)
            .where(ProjectionAccountBalance.scenario_id == scenario_id)
            .order_by(ProjectionAccountBalance.year, ProjectionAccountBalance.account_id)
        ).all()
    )
    warnings = list(
        session.scalars(
            select(ProjectionWarning)
            .where(ProjectionWarning.scenario_id == scenario_id)
            .order_by(ProjectionWarning.year)
        ).all()
    )
    return ProjectionRead(
        metadata=ProjectionRunMetadataRead.model_validate(metadata),
        years=[ProjectionYearRead.model_validate(row) for row in years],
        account_balances=[ProjectionAccountBalanceRead.model_validate(row) for row in balances],
        warnings=[ProjectionWarningRead.model_validate(warning) for warning in warnings],
    )


def require_scenario(scenario_id: str, session: Session) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return scenario


def require_income_stream(stream_id: str, household_id: str, session: Session) -> IncomeStream:
    stream = session.get(IncomeStream, stream_id)
    if stream is None or stream.household_id != household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Income stream not found")
    return stream


def require_expense_stream(stream_id: str, household_id: str, session: Session) -> ExpenseStream:
    stream = session.get(ExpenseStream, stream_id)
    if stream is None or stream.household_id != household_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense stream not found",
        )
    return stream


def require_household_account(account_id: str, household_id: str, session: Session) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.household_id != household_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account")
    return account


def get_or_create_assumptions(scenario: Scenario, session: Session) -> AssumptionSet:
    assumptions = session.scalar(
        select(AssumptionSet).where(AssumptionSet.scenario_id == scenario.id)
    )
    if assumptions is None:
        household = session.get(Household, scenario.household_id)
        assumptions = AssumptionSet(
            id=new_id(),
            scenario_id=scenario.id,
            engine_version="0.1.0",
            state="MA" if household is None else household.state,
        )
        session.add(assumptions)
        session.commit()
        session.refresh(assumptions)
    return assumptions


def get_or_create_withdrawal_strategy(
    scenario: Scenario,
    session: Session,
) -> WithdrawalStrategy:
    strategy = session.scalar(
        select(WithdrawalStrategy).where(WithdrawalStrategy.scenario_id == scenario.id)
    )
    if strategy is None:
        strategy = WithdrawalStrategy(
            id=new_id(),
            scenario_id=scenario.id,
            order_json=json.dumps(DEFAULT_WITHDRAWAL_ORDER),
        )
        session.add(strategy)
        session.commit()
        session.refresh(strategy)
    return strategy


def load_scenario_for_projection(scenario_id: str, session: Session) -> Scenario:
    scenario = session.scalar(
        select(Scenario)
        .where(Scenario.id == scenario_id)
        .options(selectinload(Scenario.household).selectinload(Household.people))
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return scenario


def build_projection_input(
    scenario: Scenario,
    assumptions: AssumptionSet,
    session: Session,
) -> ScenarioInput:
    people = [
        EnginePerson(id=person.id, dob_year=parse_year(person.dob))
        for person in scenario.household.people
    ]
    primary = next((person for person in scenario.household.people if person.is_primary), None)
    if primary is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No primary person")
    accounts = list(
        session.scalars(
            select(Account)
            .where(Account.household_id == scenario.household_id)
            .options(selectinload(Account.roth_basis), selectinload(Account.roth_conversion_lots))
        ).all()
    )
    account_states = [account_to_engine_state(account) for account in accounts]
    income_streams = [
        EngineIncomeStream(
            id=stream.id,
            person_id=stream.person_id,
            kind=stream.kind,
            annual_amount=stream.annual_amount,
            start_year=stream.start_year,
            end_year=stream.end_year,
            inflation_kind=stream.inflation_kind,
            custom_inflation_rate=stream.custom_inflation_rate,
            is_taxable_federal=stream.is_taxable_federal,
            is_taxable_state=stream.is_taxable_state,
            claiming_age=stream.claiming_age,
        )
        for stream in session.scalars(
            select(IncomeStream).where(IncomeStream.household_id == scenario.household_id)
        ).all()
    ]
    expense_streams = [
        EngineExpenseStream(
            id=stream.id,
            kind=stream.kind,
            annual_amount=stream.annual_amount,
            start_year=stream.start_year,
            end_year=stream.end_year,
            inflation_kind=stream.inflation_kind,
            custom_inflation_rate=stream.custom_inflation_rate,
        )
        for stream in session.scalars(
            select(ExpenseStream).where(ExpenseStream.household_id == scenario.household_id)
        ).all()
    ]
    strategy = get_or_create_withdrawal_strategy(scenario, session)
    people_by_id = {p.id: p for p in scenario.household.people}
    accounts_by_id = {a.id: a for a in accounts}
    sepp_plans = []
    for plan in session.scalars(select(SeppPlan).where(SeppPlan.scenario_id == scenario.id)).all():
        annual_payment = plan.initial_annual_payment_locked
        if annual_payment is None:
            acct = accounts_by_id.get(plan.account_id)
            owner = people_by_id.get(acct.owner_person_id) if acct else None
            if owner is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SEPP plan {plan.id}: account owner not found; cannot compute annual payment.",
                )
            try:
                calc = _compute_sepp_payment(
                    SeppCalculationInput(
                        method=plan.method,
                        account_balance_at_valuation=plan.account_balance_at_valuation,
                        valuation_date=date.fromisoformat(plan.valuation_date),
                        first_payment_date=date.fromisoformat(plan.first_payment_date),
                        dob=date.fromisoformat(owner.dob),
                        beneficiary_dob=None,
                        selected_interest_rate=plan.selected_interest_rate,
                        afr_prior_month=plan.afr_prior_month,
                        afr_two_months_prior=plan.afr_two_months_prior,
                        irs_data_version=assumptions.irs_data_version,
                        mortality_table_version=plan.mortality_table_version,
                    )
                )
                annual_payment = calc.annual_payment
            except (ValueError, KeyError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SEPP plan {plan.id}: could not compute annual payment — {exc}",
                ) from exc
        sepp_plans.append(
            SeppProjectionPlan(
                id=plan.id,
                account_id=plan.account_id,
                method=plan.method,
                status=plan.status,
                start_year=parse_year(plan.first_payment_date),
                required_end_year=parse_year(plan.required_end_date),
                annual_payment=annual_payment,
            )
        )
    roth_plans = [
        EngineRothConversionPlan(
            source_account_id=plan.source_account_id,
            destination_account_id=plan.destination_account_id,
            year=plan.year,
            amount=plan.amount,
            tax_payment_source_account_id=plan.tax_payment_source_account_id,
        )
        for plan in session.scalars(
            select(RothConversionPlan).where(RothConversionPlan.scenario_id == scenario.id)
        ).all()
    ]
    end_year = max(
        parse_year(person.dob) + person.life_expectancy_age
        for person in scenario.household.people
    )
    return ScenarioInput(
        id=scenario.id,
        filing_status=scenario.household.filing_status,
        state=assumptions.state,
        start_year=datetime.now(UTC).year,
        end_year=end_year,
        primary_person_id=primary.id,
        people=people,
        accounts=account_states,
        income_streams=income_streams,
        expense_streams=expense_streams,
        assumptions=EngineAssumptionSet(
            cpi_rate=assumptions.cpi_rate,
            healthcare_inflation_rate=assumptions.healthcare_inflation_rate,
            ss_cola_rate=assumptions.ss_cola_rate,
            pension_cola_rate=assumptions.pension_cola_rate,
            cash_reserve_target_months=assumptions.cash_reserve_target_months,
            tax_iteration_max=assumptions.tax_iteration_max,
            tax_iteration_tolerance=assumptions.tax_iteration_tolerance,
        ),
        withdrawal_order=json.loads(strategy.order_json),
        surplus_target_account_id=find_surplus_target_account_id(
            strategy.surplus_target,
            account_states,
        ),
        sepp_plans=sepp_plans,
        roth_conversion_plans=roth_plans,
    )


def account_to_engine_state(account: Account) -> AccountYearState:
    roth_basis = account.roth_basis
    return AccountYearState(
        id=account.id,
        owner_person_id=account.owner_person_id,
        account_type=account.account_type,
        balance=account.current_balance,
        expected_return=account.expected_return,
        cost_basis_pct=account.cost_basis_pct,
        roth_first_contribution_year=account.roth_first_contribution_year,
        roth_contributions_basis=(
            Decimal("0") if roth_basis is None else roth_basis.contributions_basis
        ),
        roth_earnings_balance=Decimal("0") if roth_basis is None else roth_basis.earnings_balance,
        roth_conversion_lots=[
            RothConversionLotState(
                conversion_year=lot.conversion_year,
                amount=lot.converted_amount,
            )
            for lot in account.roth_conversion_lots
        ],
        hsa_qualified_medical_expense_pct=(
            account.hsa_qualified_medical_expense_pct or Decimal("1")
        ),
    )


def find_surplus_target_account_id(
    surplus_target: str,
    accounts: list[AccountYearState],
) -> str | None:
    exact = next((account.id for account in accounts if account.id == surplus_target), None)
    if exact is not None:
        return exact
    return next(
        (account.id for account in accounts if account.account_type == surplus_target),
        None,
    )


def clear_projection_output(scenario_id: str, session: Session) -> None:
    for model in (
        ProjectionWarning,
        ProjectionAccountBalance,
        ProjectionYear,
        ProjectionRunMetadata,
    ):
        session.execute(delete(model).where(model.scenario_id == scenario_id))
