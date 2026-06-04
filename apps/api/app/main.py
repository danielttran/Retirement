from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from planner_engine.annuity import estimate_lifetime_annuity_income
from planner_engine.common import AccountYearState, RothConversionLotState
from planner_engine.common import Person as EnginePerson
from planner_engine.projection import (
    AssumptionSet as EngineAssumptionSet,
)
from planner_engine.projection import (
    ContributionPlan as EngineContributionPlan,
)
from planner_engine.projection import (
    ExpenseStream as EngineExpenseStream,
)
from planner_engine.projection import (
    IncomeStream as EngineIncomeStream,
)
from planner_engine.projection import (
    MoneyFlowPlan as EngineMoneyFlowPlan,
)
from planner_engine.projection import (
    ScenarioInput,
    SeppProjectionPlan,
    compute_summary,
    run_projection,
)
from planner_engine.roth import RothConversionPlan as EngineRothConversionPlan
from planner_engine.sepp.calculator import SeppCalculationInput
from planner_engine.sepp.calculator import calculate_initial_payment as _compute_sepp_payment
from planner_engine.socialsecurity import (
    explore_claiming_ages,
    full_retirement_age_months,
    pia_from_benefit,
)
from planner_engine.tax import estimate_aca_annual, estimate_medicare_annual
from planner_engine.withdrawal import DEFAULT_WITHDRAWAL_ORDER
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.database import DATABASE_PATH, get_session, init_db
from app.insights import compute_insights
from app.models import (
    Account,
    AssumptionSet,
    Contribution,
    ExpenseStream,
    Household,
    IncomeStream,
    MoneyFlow,
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
from app.montecarlo import run_monte_carlo
from app.roth_explorer import ConversionSuggestion, suggest_roth_conversions
from app.schemas import (
    AcaEstimateRead,
    AccountCreate,
    AccountRead,
    AlertRead,
    AnnuityEstimateRead,
    AssumptionSetRead,
    AssumptionSetUpdate,
    ClaimingOptionRead,
    ContributionCreate,
    ContributionRead,
    ConversionSuggestionRead,
    ExpenseStreamCreate,
    ExpenseStreamRead,
    HouseholdCreate,
    HouseholdRead,
    IncomeStreamCreate,
    IncomeStreamRead,
    InsightsRead,
    MedicareEstimateRead,
    MoneyFlowCreate,
    MoneyFlowRead,
    MonteCarloRead,
    PersonCreate,
    ProjectionAccountBalanceRead,
    ProjectionRead,
    ProjectionRunMetadataRead,
    ProjectionSummaryRead,
    ProjectionWarningRead,
    ProjectionYearRead,
    RothConversionPlanCreate,
    RothConversionPlanRead,
    RothExplorerRead,
    ScenarioDetail,
    ScenarioRead,
    ScoreComponentRead,
    SeppMethod,
    SeppPlanCreate,
    SeppPlanRead,
    SocialSecurityExplorerRead,
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


@app.get("/calculators/annuity", response_model=AnnuityEstimateRead, tags=["calculators"])
def annuity_estimate(premium: Decimal, age: int) -> AnnuityEstimateRead:
    from planner_engine.annuity import payout_rate

    return AnnuityEstimateRead(
        premium=premium,
        age=age,
        payout_rate=payout_rate(age),
        annual_income=estimate_lifetime_annuity_income(premium, age),
    )


@app.get("/calculators/aca", response_model=AcaEstimateRead, tags=["calculators"])
def aca_estimate(age: int) -> AcaEstimateRead:
    return AcaEstimateRead(age=age, annual_per_person=estimate_aca_annual(age))


@app.get("/calculators/medicare", response_model=MedicareEstimateRead, tags=["calculators"])
def medicare_estimate(
    health: str = "good",
    include_dental_vision: bool = True,
) -> MedicareEstimateRead:
    return MedicareEstimateRead(
        health=health,
        annual_per_person=estimate_medicare_annual(health, include_dental_vision),
        include_dental_vision=include_dental_vision,
    )


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


@app.post(
    "/households/{household_id}/people",
    response_model=HouseholdRead,
    status_code=status.HTTP_201_CREATED,
    tags=["households"],
)
def add_person(household_id: str, payload: PersonCreate, session: SessionDep) -> Household:
    household = session.get(Household, household_id)
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    person = Person(
        id=new_id(),
        household_id=household_id,
        name=payload.name,
        dob=payload.dob,
        retirement_date=payload.retirement_date,
        life_expectancy_age=payload.life_expectancy_age,
        death_age=payload.death_age,
        is_primary=False,
    )
    session.add(person)
    session.commit()
    session.refresh(household)
    return household


@app.delete(
    "/households/{household_id}/people/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["households"],
)
def delete_person(household_id: str, person_id: str, session: SessionDep) -> Response:
    person = session.get(Person, person_id)
    if person is None or person.household_id != household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    if person.is_primary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the primary person"
        )
    session.delete(person)
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


@app.get(
    "/scenarios/{scenario_id}/contributions",
    response_model=list[ContributionRead],
    tags=["contributions"],
)
def list_contributions(scenario_id: str, session: SessionDep) -> list[Contribution]:
    require_scenario(scenario_id, session)
    return list(
        session.scalars(
            select(Contribution).where(Contribution.scenario_id == scenario_id)
        ).all()
    )


@app.post(
    "/scenarios/{scenario_id}/contributions",
    response_model=ContributionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["contributions"],
)
def create_contribution(
    scenario_id: str,
    payload: ContributionCreate,
    session: SessionDep,
) -> Contribution:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.account_id, scenario.household_id, session)
    contribution = Contribution(id=new_id(), scenario_id=scenario.id, **payload.model_dump())
    session.add(contribution)
    session.commit()
    session.refresh(contribution)
    return contribution


@app.put(
    "/scenarios/{scenario_id}/contributions/{contribution_id}",
    response_model=ContributionRead,
    tags=["contributions"],
)
def update_contribution(
    scenario_id: str,
    contribution_id: str,
    payload: ContributionCreate,
    session: SessionDep,
) -> Contribution:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.account_id, scenario.household_id, session)
    contribution = session.get(Contribution, contribution_id)
    if contribution is None or contribution.scenario_id != scenario_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contribution not found")
    for key, value in payload.model_dump().items():
        setattr(contribution, key, value)
    session.commit()
    session.refresh(contribution)
    return contribution


@app.delete(
    "/scenarios/{scenario_id}/contributions/{contribution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["contributions"],
)
def delete_contribution(
    scenario_id: str, contribution_id: str, session: SessionDep
) -> Response:
    require_scenario(scenario_id, session)
    contribution = session.get(Contribution, contribution_id)
    if contribution is None or contribution.scenario_id != scenario_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contribution not found")
    session.delete(contribution)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/scenarios/{scenario_id}/money-flows",
    response_model=list[MoneyFlowRead],
    tags=["money-flows"],
)
def list_money_flows(scenario_id: str, session: SessionDep) -> list[MoneyFlow]:
    require_scenario(scenario_id, session)
    return list(
        session.scalars(select(MoneyFlow).where(MoneyFlow.scenario_id == scenario_id)).all()
    )


@app.post(
    "/scenarios/{scenario_id}/money-flows",
    response_model=MoneyFlowRead,
    status_code=status.HTTP_201_CREATED,
    tags=["money-flows"],
)
def create_money_flow(
    scenario_id: str, payload: MoneyFlowCreate, session: SessionDep
) -> MoneyFlow:
    scenario = require_scenario(scenario_id, session)
    require_household_account(payload.from_account_id, scenario.household_id, session)
    require_household_account(payload.to_account_id, scenario.household_id, session)
    flow = MoneyFlow(id=new_id(), scenario_id=scenario.id, **payload.model_dump())
    session.add(flow)
    session.commit()
    session.refresh(flow)
    return flow


@app.delete(
    "/scenarios/{scenario_id}/money-flows/{flow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["money-flows"],
)
def delete_money_flow(scenario_id: str, flow_id: str, session: SessionDep) -> Response:
    require_scenario(scenario_id, session)
    flow = session.get(MoneyFlow, flow_id)
    if flow is None or flow.scenario_id != scenario_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Money flow not found")
    session.delete(flow)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/scenarios/{scenario_id}/run-projection",
    response_model=ProjectionRead,
    tags=["projection"],
)
def run_scenario_projection(
    scenario_id: str,
    session: SessionDep,
    variant: str = "average",
) -> ProjectionRead:
    scenario = load_scenario_for_projection(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    projection_input = apply_rate_variant(
        build_projection_input(scenario, assumptions, session), variant
    )
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
            ordinary_taxable_income=row.ordinary_taxable_income,
            medicare_irmaa=row.medicare_irmaa,
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


@app.post(
    "/scenarios/{scenario_id}/monte-carlo",
    response_model=MonteCarloRead,
    tags=["projection"],
)
def run_scenario_monte_carlo(
    scenario_id: str,
    session: SessionDep,
    trials: int = 500,
) -> MonteCarloRead:
    trials = max(50, min(2000, trials))
    scenario = load_scenario_for_projection(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    projection_input = build_projection_input(scenario, assumptions, session)
    result = run_monte_carlo(
        projection_input,
        assumptions.irs_data_version,
        assumptions.engine_version,
        trials=trials,
        seed=12345,
    )
    return MonteCarloRead(**result.__dict__)


@app.post(
    "/scenarios/{scenario_id}/roth-explorer",
    response_model=RothExplorerRead,
    tags=["roth"],
)
def run_roth_explorer(
    scenario_id: str,
    session: SessionDep,
    strategy: str = "bracket",
    target_rate: Decimal = Decimal("0.24"),
    irmaa_magi_ceiling: Decimal = Decimal("206000"),
    start_year: int | None = None,
    end_year: int | None = None,
    apply: bool = False,
) -> RothExplorerRead:
    scenario = load_scenario_for_projection(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    projection_input = build_projection_input(scenario, assumptions, session)
    window_start = start_year if start_year is not None else projection_input.start_year
    # Default to the year before the primary reaches RMD age 73; conversions before RMDs help most.
    primary = next((p for p in scenario.household.people if p.is_primary), None)
    default_end = projection_input.end_year
    if primary is not None:
        default_end = min(default_end, parse_year(primary.dob) + 72)
    window_end = end_year if end_year is not None else max(window_start, default_end)

    result = suggest_roth_conversions(
        projection_input,
        assumptions.irs_data_version,
        assumptions.engine_version,
        strategy=strategy,
        target_rate=target_rate,
        irmaa_magi_ceiling=irmaa_magi_ceiling,
        start_year=window_start,
        end_year=window_end,
    )

    if apply and result.source_account_id and result.destination_account_id:
        for suggestion in result.suggestions:
            session.add(
                RothConversionPlan(
                    id=new_id(),
                    scenario_id=scenario.id,
                    source_account_id=result.source_account_id,
                    destination_account_id=result.destination_account_id,
                    year=suggestion.year,
                    amount=suggestion.amount,
                )
            )
        session.commit()

    return RothExplorerRead(
        strategy=result.strategy,
        source_account_id=result.source_account_id,
        destination_account_id=result.destination_account_id,
        suggestions=[_suggestion_read(s) for s in result.suggestions],
        total_converted=result.total_converted,
        baseline_lifetime_tax=result.baseline_lifetime_tax,
        projected_lifetime_tax=result.projected_lifetime_tax,
        baseline_estate=result.baseline_estate,
        projected_estate=result.projected_estate,
        note=result.note,
    )


@app.get(
    "/scenarios/{scenario_id}/insights",
    response_model=InsightsRead,
    tags=["projection"],
)
def scenario_insights(scenario_id: str, session: SessionDep) -> InsightsRead:
    scenario = load_scenario_for_projection(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    projection_input = build_projection_input(scenario, assumptions, session)
    run = run_projection(
        projection_input, assumptions.irs_data_version, assumptions.engine_version
    )
    monte_carlo = run_monte_carlo(
        projection_input,
        assumptions.irs_data_version,
        assumptions.engine_version,
        trials=300,
        seed=12345,
    )
    primary = next((p for p in scenario.household.people if p.is_primary), None)
    life_expectancy = primary.life_expectancy_age if primary else run.summary.final_age
    result = compute_insights(projection_input, run, monte_carlo, life_expectancy)
    return InsightsRead(
        score=result.score,
        rating=result.rating,
        components=[
            ScoreComponentRead(
                label=c.label, score=c.score, weight=c.weight, detail=c.detail
            )
            for c in result.components
        ],
        alerts=[
            AlertRead(severity=a.severity, title=a.title, message=a.message)
            for a in result.alerts
        ],
    )


@app.get(
    "/scenarios/{scenario_id}/social-security-explorer",
    response_model=SocialSecurityExplorerRead,
    tags=["social-security"],
)
def social_security_explorer(
    scenario_id: str,
    session: SessionDep,
    person_id: str | None = None,
) -> SocialSecurityExplorerRead:
    scenario = load_scenario_for_projection(scenario_id, session)
    assumptions = get_or_create_assumptions(scenario, session)
    people = scenario.household.people
    person = None
    if person_id is not None:
        person = next((p for p in people if p.id == person_id), None)
    if person is None:
        person = next((p for p in people if p.is_primary), people[0] if people else None)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No person found")

    ss_stream = session.scalar(
        select(IncomeStream).where(
            IncomeStream.household_id == scenario.household_id,
            IncomeStream.person_id == person.id,
            IncomeStream.kind == "social_security",
        )
    )
    birth_year = parse_year(person.dob)
    fra_months = full_retirement_age_months(birth_year)
    if ss_stream is not None:
        claiming_age = ss_stream.claiming_age or (fra_months // 12)
        pia = pia_from_benefit(ss_stream.annual_amount, claiming_age, fra_months)
    else:
        claiming_age = None
        pia = Decimal("0")

    result = explore_claiming_ages(
        pia_annual=pia,
        birth_year=birth_year,
        life_expectancy_age=person.life_expectancy_age,
        cola_rate=assumptions.ss_cola_rate,
    )
    return SocialSecurityExplorerRead(
        person_id=person.id,
        person_name=person.name,
        pia_annual=result.pia_annual,
        full_retirement_age_months=result.full_retirement_age_months,
        current_claiming_age=claiming_age,
        options=[
            ClaimingOptionRead(
                claiming_age=o.claiming_age,
                monthly_benefit=o.monthly_benefit,
                annual_benefit=o.annual_benefit,
                lifetime_total=o.lifetime_total,
                break_even_age_vs_earliest=o.break_even_age_vs_earliest,
            )
            for o in result.options
        ],
        max_lifetime_claiming_age=result.max_lifetime_claiming_age,
    )


def _suggestion_read(suggestion: ConversionSuggestion) -> ConversionSuggestionRead:
    return ConversionSuggestionRead(
        year=suggestion.year,
        amount=suggestion.amount,
        ordinary_taxable_income=suggestion.ordinary_taxable_income,
        magi=suggestion.magi,
        headroom=suggestion.headroom,
        traditional_balance=suggestion.traditional_balance,
    )


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
    scenario = session.get(Scenario, scenario_id)
    illiquid_ids: set[str] = set()
    if scenario is not None:
        illiquid_ids = {
            account.id
            for account in session.scalars(
                select(Account).where(Account.household_id == scenario.household_id)
            ).all()
            if account.account_type in {"real_estate", "debt"}
        }
    summary = compute_summary(years, balances, illiquid_ids)
    return ProjectionRead(
        metadata=ProjectionRunMetadataRead.model_validate(metadata),
        years=[ProjectionYearRead.model_validate(row) for row in years],
        account_balances=[ProjectionAccountBalanceRead.model_validate(row) for row in balances],
        warnings=[ProjectionWarningRead.model_validate(warning) for warning in warnings],
        summary=None if summary is None else ProjectionSummaryRead(**summary.__dict__),
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
        EnginePerson(
            id=person.id,
            dob_year=parse_year(person.dob),
            # A person is modeled to die at an explicit death age, else their life expectancy.
            death_year=parse_year(person.dob)
            + (person.death_age if person.death_age is not None else person.life_expectancy_age),
        )
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
    # Apply the global housing appreciation assumption to real-estate accounts.
    for state in account_states:
        if state.account_type == "real_estate":
            state.expected_return = assumptions.housing_appreciation_rate
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
            survivor_pct=stream.survivor_pct,
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
                    detail=(
                        f"SEPP plan {plan.id}: account owner not found; "
                        "cannot compute annual payment."
                    ),
                )
            try:
                calc = _compute_sepp_payment(
                    SeppCalculationInput(
                        method=cast(SeppMethod, plan.method),
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
    contribution_plans = [
        EngineContributionPlan(
            account_id=contribution.account_id,
            annual_amount=contribution.annual_amount,
            start_year=contribution.start_year,
            end_year=contribution.end_year,
            inflation_kind=contribution.inflation_kind,
            custom_inflation_rate=contribution.custom_inflation_rate,
            employer_match_amount=contribution.employer_match_amount,
        )
        for contribution in session.scalars(
            select(Contribution).where(Contribution.scenario_id == scenario.id)
        ).all()
    ]
    money_flows = [
        EngineMoneyFlowPlan(
            from_account_id=flow.from_account_id,
            to_account_id=flow.to_account_id,
            year=flow.year,
            amount=flow.amount,
        )
        for flow in session.scalars(
            select(MoneyFlow).where(MoneyFlow.scenario_id == scenario.id)
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
        spouse_person_id=next(
            (p.id for p in scenario.household.people if not p.is_primary), None
        ),
        people=people,
        accounts=account_states,
        income_streams=income_streams,
        expense_streams=expense_streams,
        assumptions=EngineAssumptionSet(
            cpi_rate=assumptions.cpi_rate,
            healthcare_inflation_rate=assumptions.healthcare_inflation_rate,
            ss_cola_rate=assumptions.ss_cola_rate,
            pension_cola_rate=assumptions.pension_cola_rate,
            bracket_indexing_rate=assumptions.bracket_indexing_rate,
            itemized_deductions=assumptions.itemized_deductions,
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
        contribution_plans=contribution_plans,
        money_flows=money_flows,
    )


# Account types whose returns shift under optimistic/pessimistic assumption sets.
_VARIANT_VOLATILE_TYPES = {
    "taxable_brokerage",
    "traditional_ira",
    "traditional_401k",
    "traditional_403b",
    "governmental_457b",
    "roth_ira",
    "roth_401k",
    "hsa",
    "real_estate",
}
_DEFAULT_VARIANT_DELTA = Decimal("0.02")
_VARIANT_CPI_DELTA = Decimal("0.005")


def apply_rate_variant(scenario: ScenarioInput, variant: str) -> ScenarioInput:
    """Return a scenario adjusted for Boldin-style optimistic/average/pessimistic assumptions.

    Optimistic raises returns and lowers inflation; pessimistic does the reverse. "average" is the
    unmodified scenario. The return shift uses each account's own stddev when set, else a default.
    """
    if variant not in {"optimistic", "pessimistic"}:
        return scenario
    sign = Decimal("1") if variant == "optimistic" else Decimal("-1")
    overrides: dict[str, dict[int, Decimal]] = {}
    years = range(scenario.start_year, scenario.end_year + 1)
    for account in scenario.accounts:
        if account.account_type not in _VARIANT_VOLATILE_TYPES:
            continue
        delta = account.return_stddev if account.return_stddev else _DEFAULT_VARIANT_DELTA
        rate = account.expected_return + sign * delta
        overrides[account.id] = {year: rate for year in years}
    cpi = scenario.assumptions.cpi_rate - sign * _VARIANT_CPI_DELTA
    if cpi < Decimal("0"):
        cpi = Decimal("0")
    new_assumptions = replace(scenario.assumptions, cpi_rate=cpi)
    return replace(scenario, assumptions=new_assumptions, return_overrides=overrides)


def account_to_engine_state(account: Account) -> AccountYearState:
    roth_basis = account.roth_basis
    return AccountYearState(
        id=account.id,
        owner_person_id=account.owner_person_id,
        account_type=account.account_type,
        balance=account.current_balance,
        expected_return=account.expected_return,
        return_stddev=account.return_stddev,
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
        debt_annual_payment=account.debt_annual_payment or Decimal("0"),
        exclude_from_withdrawals=account.exclude_from_withdrawals,
        sale_year=account.sale_year,
        selling_cost_pct=(
            account.selling_cost_pct if account.selling_cost_pct is not None else Decimal("0.06")
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
