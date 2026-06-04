"""Comprehensive API tests covering all endpoints in apps/api/app/main.py."""
from __future__ import annotations

import json
from collections.abc import Generator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import app.models  # noqa: F401
import pytest
from app.database import Base, get_session
from app.main import app, find_surplus_target_account_id, new_id, now_iso, parse_year
from fastapi.testclient import TestClient
from planner_engine.common import AccountYearState
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

CURRENT_YEAR = datetime.now(UTC).year


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_session() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def household_payload() -> dict:
    return {
        "name": "Smith Family",
        "filing_status": "single",
        "state": "MA",
        "primary_person": {
            "name": "Jordan",
            "dob": "1975-04-15",
            "life_expectancy_age": 85,
        },
        "scenario_name": "Baseline",
    }


@pytest.fixture()
def scenario(client: TestClient, household_payload: dict) -> dict:
    resp = client.post("/households", json=household_payload)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def scenario_with_account(client: TestClient, scenario: dict) -> dict:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Savings",
            "account_type": "cash",
            "current_balance": "200000",
            "expected_return": "0",
        },
    )
    assert resp.status_code == 201
    return {"scenario": scenario, "account": resp.json()}


@pytest.fixture()
def roth_accounts(client: TestClient) -> dict:
    """Create traditional IRA, Roth IRA, and cash accounts.
    Uses life_expectancy_age=80 to stay within the IRS uniform lifetime table (max age 80).
    """
    hh_resp = client.post(
        "/households",
        json={
            "name": "Roth Test HH",
            "filing_status": "single",
            "state": "MA",
            "primary_person": {
                "name": "Casey",
                "dob": "1975-01-01",
                "life_expectancy_age": 80,
            },
            "scenario_name": "Roth Scenario",
        },
    )
    assert hh_resp.status_code == 201
    scenario = hh_resp.json()
    person_id = scenario["household"]["people"][0]["id"]
    sid = scenario["id"]
    trad = client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Traditional IRA",
            "account_type": "traditional_ira",
            "current_balance": "100000",
            "expected_return": "0.06",
        },
    )
    roth = client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Roth IRA",
            "account_type": "roth_ira",
            "current_balance": "50000",
            "expected_return": "0.07",
            "roth_first_contribution_year": 2015,
        },
    )
    cash = client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Cash",
            "account_type": "cash",
            "current_balance": "20000",
            "expected_return": "0",
        },
    )
    assert trad.status_code == roth.status_code == cash.status_code == 201
    return {
        "scenario": scenario,
        "trad_id": trad.json()["id"],
        "roth_id": roth.json()["id"],
        "cash_id": cash.json()["id"],
    }


# ---------------------------------------------------------------------------
# Utility function unit tests
# ---------------------------------------------------------------------------


def test_parse_year_full_date() -> None:
    assert parse_year("2024-01-01") == 2024


def test_parse_year_mid_year_date() -> None:
    assert parse_year("1975-04-15") == 1975


def test_new_id_returns_uuid_string() -> None:
    result = new_id()
    assert isinstance(result, str)
    assert len(result) == 36


def test_new_id_is_unique() -> None:
    assert new_id() != new_id()


def test_now_iso_returns_iso_string() -> None:
    result = now_iso()
    assert isinstance(result, str)
    assert "T" in result


def test_find_surplus_target_exact_id_match() -> None:
    accts = [
        AccountYearState(
            id="abc123", owner_person_id="p1", account_type="cash",
            balance=Decimal("0"), expected_return=Decimal("0"),
        )
    ]
    assert find_surplus_target_account_id("abc123", accts) == "abc123"


def test_find_surplus_target_by_account_type() -> None:
    accts = [
        AccountYearState(
            id="xyz", owner_person_id="p1", account_type="taxable_brokerage",
            balance=Decimal("0"), expected_return=Decimal("0"),
        )
    ]
    assert find_surplus_target_account_id("taxable_brokerage", accts) == "xyz"


def test_find_surplus_target_no_match_returns_none() -> None:
    accts = [
        AccountYearState(
            id="abc", owner_person_id="p1", account_type="cash",
            balance=Decimal("0"), expected_return=Decimal("0"),
        )
    ]
    assert find_surplus_target_account_id("taxable_brokerage", accts) is None


def test_find_surplus_target_empty_list() -> None:
    assert find_surplus_target_account_id("cash", []) is None


def test_find_surplus_target_id_takes_precedence_over_type() -> None:
    """Exact ID match wins over type match."""
    accts = [
        AccountYearState(
            id="exact-id", owner_person_id="p1", account_type="taxable_brokerage",
            balance=Decimal("0"), expected_return=Decimal("0"),
        ),
        AccountYearState(
            id="other-id", owner_person_id="p1", account_type="taxable_brokerage",
            balance=Decimal("0"), expected_return=Decimal("0"),
        ),
    ]
    assert find_surplus_target_account_id("exact-id", accts) == "exact-id"


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_database_info(client: TestClient) -> None:
    resp = client.get("/system/database")
    assert resp.status_code == 200
    assert "path" in resp.json()


def test_openapi_json_lists_key_routes(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/health" in paths
    assert "/households" in paths
    assert "/scenarios/{scenario_id}/run-projection" in paths
    assert "/scenarios/{scenario_id}/roth-conversions" in paths


# ---------------------------------------------------------------------------
# Household endpoints
# ---------------------------------------------------------------------------


def test_list_households_empty(client: TestClient) -> None:
    assert client.get("/households").json() == []


def test_create_household_201(client: TestClient, household_payload: dict) -> None:
    resp = client.post("/households", json=household_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Baseline"
    assert data["household"]["name"] == "Smith Family"
    assert data["household"]["filing_status"] == "single"
    assert len(data["household"]["people"]) == 1
    assert data["household"]["people"][0]["name"] == "Jordan"
    assert data["household"]["people"][0]["is_primary"] is True


def test_create_household_mfj(client: TestClient) -> None:
    resp = client.post(
        "/households",
        json={
            "name": "Joint",
            "filing_status": "mfj",
            "state": "TX",
            "primary_person": {"name": "Pat", "dob": "1970-01-01", "life_expectancy_age": 90},
            "scenario_name": "Primary",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["household"]["filing_status"] == "mfj"


def test_list_households_after_create(
    client: TestClient, household_payload: dict
) -> None:
    client.post("/households", json=household_payload)
    resp = client.get("/households")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_household_seeds_assumptions(
    client: TestClient, scenario: dict
) -> None:
    resp = client.get(f"/scenarios/{scenario['id']}/assumptions")
    assert resp.status_code == 200
    assert resp.json()["cpi_rate"] == "0.025"


def test_create_household_seeds_withdrawal_strategy(
    client: TestClient, scenario: dict
) -> None:
    resp = client.get(f"/scenarios/{scenario['id']}/withdrawal-strategy")
    assert resp.status_code == 200
    order = json.loads(resp.json()["order_json"])
    assert isinstance(order, list) and len(order) > 0


# ---------------------------------------------------------------------------
# Scenario endpoints
# ---------------------------------------------------------------------------


def test_list_scenarios_empty(client: TestClient) -> None:
    assert client.get("/scenarios").json() == []


def test_list_scenarios_after_create(client: TestClient, scenario: dict) -> None:
    resp = client.get("/scenarios")
    assert resp.status_code == 200
    assert any(s["id"] == scenario["id"] for s in resp.json())


def test_get_scenario(client: TestClient, scenario: dict) -> None:
    resp = client.get(f"/scenarios/{scenario['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == scenario["id"]
    assert resp.json()["name"] == "Baseline"


def test_get_scenario_not_found(client: TestClient) -> None:
    assert client.get("/scenarios/nonexistent-id").status_code == 404


def test_get_scenario_includes_total_balance(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    data = client.get(f"/scenarios/{sid}").json()
    assert Decimal(data["total_account_balance"]) == Decimal("200000")


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------


def test_list_accounts_empty(client: TestClient, scenario: dict) -> None:
    assert client.get(f"/scenarios/{scenario['id']}/accounts").json() == []


def test_list_accounts_scenario_not_found(client: TestClient) -> None:
    assert client.get("/scenarios/bad-id/accounts").status_code == 404


def test_create_account_cash(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Emergency Fund",
            "account_type": "cash",
            "current_balance": "50000",
            "expected_return": "0.02",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "cash"
    assert resp.json()["current_balance"] == "50000"


def test_create_account_taxable_brokerage(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Taxable",
            "account_type": "taxable_brokerage",
            "current_balance": "100000",
            "expected_return": "0.07",
            "cost_basis_pct": "0.60",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["cost_basis_pct"] == "0.60"


def test_create_taxable_requires_cost_basis(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Taxable",
            "account_type": "taxable_brokerage",
            "current_balance": "100000",
            "expected_return": "0.07",
        },
    )
    assert resp.status_code == 400


def test_create_roth_ira(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Roth IRA",
            "account_type": "roth_ira",
            "current_balance": "75000",
            "expected_return": "0.07",
            "roth_first_contribution_year": 2010,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["roth_first_contribution_year"] == 2010


def test_create_roth_requires_contribution_year(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Roth IRA",
            "account_type": "roth_ira",
            "current_balance": "75000",
            "expected_return": "0.07",
        },
    )
    assert resp.status_code == 400


def test_create_account_invalid_owner(client: TestClient, scenario: dict) -> None:
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": "bad-person-id",
            "name": "Bad Account",
            "account_type": "cash",
            "current_balance": "1000",
        },
    )
    assert resp.status_code == 400


def test_create_account_scenario_not_found(client: TestClient) -> None:
    assert (
        client.post(
            "/scenarios/bad-scenario/accounts",
            json={
                "owner_person_id": "p1",
                "name": "X",
                "account_type": "cash",
                "current_balance": "0",
            },
        ).status_code
        == 404
    )


def test_list_accounts_returns_correct_count(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    assert len(client.get(f"/scenarios/{sid}/accounts").json()) == 1


def test_update_account(client: TestClient, scenario_with_account: dict) -> None:
    sid = scenario_with_account["scenario"]["id"]
    aid = scenario_with_account["account"]["id"]
    person_id = scenario_with_account["scenario"]["household"]["people"][0]["id"]
    resp = client.put(
        f"/scenarios/{sid}/accounts/{aid}",
        json={
            "owner_person_id": person_id,
            "name": "Savings Updated",
            "account_type": "cash",
            "current_balance": "300000",
            "expected_return": "0.01",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["current_balance"] == "300000"
    assert resp.json()["name"] == "Savings Updated"


def test_update_account_bad_id_returns_400(
    client: TestClient, scenario: dict
) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.put(
        f"/scenarios/{scenario['id']}/accounts/bad-id",
        json={
            "owner_person_id": person_id,
            "name": "X",
            "account_type": "cash",
            "current_balance": "0",
        },
    )
    assert resp.status_code == 400


def test_delete_account(client: TestClient, scenario_with_account: dict) -> None:
    sid = scenario_with_account["scenario"]["id"]
    aid = scenario_with_account["account"]["id"]
    assert client.delete(f"/scenarios/{sid}/accounts/{aid}").status_code == 204
    assert client.get(f"/scenarios/{sid}/accounts").json() == []


def test_delete_account_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.delete(f"/scenarios/{scenario['id']}/accounts/bad-id").status_code == 404
    )


# ---------------------------------------------------------------------------
# Income stream endpoints
# ---------------------------------------------------------------------------


def test_list_income_streams_empty(client: TestClient, scenario: dict) -> None:
    assert client.get(f"/scenarios/{scenario['id']}/income-streams").json() == []


def test_list_income_streams_scenario_not_found(client: TestClient) -> None:
    assert client.get("/scenarios/bad-id/income-streams").status_code == 404


def test_create_income_stream(client: TestClient, scenario: dict) -> None:
    resp = client.post(
        f"/scenarios/{scenario['id']}/income-streams",
        json={
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "80000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "cpi",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Salary"
    assert data["annual_amount"] == "80000"
    assert data["kind"] == "salary"


def test_create_income_stream_social_security_with_claiming_age(
    client: TestClient, scenario: dict
) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/income-streams",
        json={
            "person_id": person_id,
            "name": "SS",
            "kind": "social_security",
            "annual_amount": "24000",
            "start_year": CURRENT_YEAR + 10,
            "inflation_kind": "ss_cola",
            "claiming_age": 67,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["claiming_age"] == 67
    assert resp.json()["person_id"] == person_id


def test_create_income_stream_invalid_person(client: TestClient, scenario: dict) -> None:
    resp = client.post(
        f"/scenarios/{scenario['id']}/income-streams",
        json={
            "person_id": "bad-person-id",
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "1000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    )
    assert resp.status_code == 400


def test_create_income_stream_scenario_not_found(client: TestClient) -> None:
    assert (
        client.post(
            "/scenarios/bad-id/income-streams",
            json={
                "name": "X",
                "kind": "salary",
                "annual_amount": "1000",
                "start_year": CURRENT_YEAR,
                "inflation_kind": "none",
            },
        ).status_code
        == 404
    )


def test_update_income_stream(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    stream_id = client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "80000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    ).json()["id"]
    resp = client.put(
        f"/scenarios/{sid}/income-streams/{stream_id}",
        json={
            "name": "Salary Updated",
            "kind": "salary",
            "annual_amount": "90000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["annual_amount"] == "90000"
    assert resp.json()["name"] == "Salary Updated"


def test_update_income_stream_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.put(
            f"/scenarios/{scenario['id']}/income-streams/bad-id",
            json={
                "name": "X",
                "kind": "salary",
                "annual_amount": "1000",
                "start_year": CURRENT_YEAR,
                "inflation_kind": "none",
            },
        ).status_code
        == 404
    )


def test_delete_income_stream(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    stream_id = client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "80000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    ).json()["id"]
    assert client.delete(f"/scenarios/{sid}/income-streams/{stream_id}").status_code == 204
    assert client.get(f"/scenarios/{sid}/income-streams").json() == []


def test_delete_income_stream_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.delete(
            f"/scenarios/{scenario['id']}/income-streams/bad-id"
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Expense stream endpoints
# ---------------------------------------------------------------------------


def test_list_expense_streams_empty(client: TestClient, scenario: dict) -> None:
    assert client.get(f"/scenarios/{scenario['id']}/expense-streams").json() == []


def test_list_expense_streams_scenario_not_found(client: TestClient) -> None:
    assert client.get("/scenarios/bad-id/expense-streams").status_code == 404


def test_create_expense_stream(client: TestClient, scenario: dict) -> None:
    resp = client.post(
        f"/scenarios/{scenario['id']}/expense-streams",
        json={
            "name": "Living",
            "kind": "must_spend",
            "annual_amount": "60000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "cpi",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Living"
    assert resp.json()["kind"] == "must_spend"


def test_create_expense_stream_scenario_not_found(client: TestClient) -> None:
    assert (
        client.post(
            "/scenarios/bad-id/expense-streams",
            json={
                "name": "X",
                "kind": "must_spend",
                "annual_amount": "1000",
                "start_year": CURRENT_YEAR,
                "inflation_kind": "none",
            },
        ).status_code
        == 404
    )


def test_update_expense_stream(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    stream_id = client.post(
        f"/scenarios/{sid}/expense-streams",
        json={
            "name": "Living",
            "kind": "must_spend",
            "annual_amount": "60000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    ).json()["id"]
    resp = client.put(
        f"/scenarios/{sid}/expense-streams/{stream_id}",
        json={
            "name": "Living Updated",
            "kind": "must_spend",
            "annual_amount": "65000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["annual_amount"] == "65000"


def test_update_expense_stream_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.put(
            f"/scenarios/{scenario['id']}/expense-streams/bad-id",
            json={
                "name": "X",
                "kind": "must_spend",
                "annual_amount": "1000",
                "start_year": CURRENT_YEAR,
                "inflation_kind": "none",
            },
        ).status_code
        == 404
    )


def test_delete_expense_stream(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    stream_id = client.post(
        f"/scenarios/{sid}/expense-streams",
        json={
            "name": "Living",
            "kind": "must_spend",
            "annual_amount": "60000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    ).json()["id"]
    assert client.delete(f"/scenarios/{sid}/expense-streams/{stream_id}").status_code == 204
    assert client.get(f"/scenarios/{sid}/expense-streams").json() == []


def test_delete_expense_stream_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.delete(
            f"/scenarios/{scenario['id']}/expense-streams/bad-id"
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Assumption endpoints
# ---------------------------------------------------------------------------


def test_get_assumptions(client: TestClient, scenario: dict) -> None:
    resp = client.get(f"/scenarios/{scenario['id']}/assumptions")
    assert resp.status_code == 200
    data = resp.json()
    assert "cpi_rate" in data
    assert "tax_iteration_max" in data
    assert "irs_data_version" in data


def test_get_assumptions_scenario_not_found(client: TestClient) -> None:
    assert client.get("/scenarios/bad-id/assumptions").status_code == 404


def test_update_assumptions(client: TestClient, scenario: dict) -> None:
    resp = client.put(
        f"/scenarios/{scenario['id']}/assumptions",
        json={
            "cpi_rate": "0.03",
            "healthcare_inflation_rate": "0.05",
            "ss_cola_rate": "0.025",
            "pension_cola_rate": "0.01",
            "bracket_indexing_rate": "0.025",
            "cash_reserve_target_months": 12,
            "irs_data_version": "2024-33",
            "engine_version": "test-v2",
            "state": "TX",
            "tax_iteration_max": 10,
            "tax_iteration_tolerance": "0.50",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cpi_rate"] == "0.03"
    assert data["state"] == "TX"
    assert data["cash_reserve_target_months"] == 12
    assert data["engine_version"] == "test-v2"


def test_update_assumptions_scenario_not_found(client: TestClient) -> None:
    assert (
        client.put(
            "/scenarios/bad-id/assumptions",
            json={
                "cpi_rate": "0.03",
                "healthcare_inflation_rate": "0.04",
                "ss_cola_rate": "0.025",
                "pension_cola_rate": "0",
                "bracket_indexing_rate": "0.025",
                "cash_reserve_target_months": 24,
                "irs_data_version": "2024-33",
                "engine_version": "test",
                "state": "MA",
                "tax_iteration_max": 5,
                "tax_iteration_tolerance": "1.00",
            },
        ).status_code
        == 404
    )


def test_update_assumptions_persists(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    client.put(
        f"/scenarios/{sid}/assumptions",
        json={
            "cpi_rate": "0.035",
            "healthcare_inflation_rate": "0.04",
            "ss_cola_rate": "0.025",
            "pension_cola_rate": "0",
            "bracket_indexing_rate": "0.025",
            "cash_reserve_target_months": 24,
            "irs_data_version": "2024-33",
            "engine_version": "test",
            "state": "MA",
            "tax_iteration_max": 5,
            "tax_iteration_tolerance": "1.00",
        },
    )
    data = client.get(f"/scenarios/{sid}/assumptions").json()
    assert data["cpi_rate"] == "0.035"


# ---------------------------------------------------------------------------
# Withdrawal strategy endpoints
# ---------------------------------------------------------------------------


def test_get_withdrawal_strategy(client: TestClient, scenario: dict) -> None:
    resp = client.get(f"/scenarios/{scenario['id']}/withdrawal-strategy")
    assert resp.status_code == 200
    data = resp.json()
    assert "order_json" in data
    assert "surplus_target" in data


def test_get_withdrawal_strategy_scenario_not_found(client: TestClient) -> None:
    assert client.get("/scenarios/bad-id/withdrawal-strategy").status_code == 404


def test_update_withdrawal_strategy(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    new_order = json.dumps(["cash", "taxable_brokerage", "traditional"])
    resp = client.put(
        f"/scenarios/{sid}/withdrawal-strategy",
        json={"order_json": new_order, "surplus_target": "taxable_brokerage"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert json.loads(data["order_json"]) == ["cash", "taxable_brokerage", "traditional"]
    assert data["surplus_target"] == "taxable_brokerage"


def test_update_withdrawal_strategy_scenario_not_found(client: TestClient) -> None:
    assert (
        client.put(
            "/scenarios/bad-id/withdrawal-strategy",
            json={"order_json": "[]", "surplus_target": "cash"},
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# SEPP plan endpoints
# ---------------------------------------------------------------------------


def _sepp_payload(account_id: str, status: str = "active") -> dict:
    return {
        "account_id": account_id,
        "method": "fixed_amortization",
        "status": status,
        "valuation_date": "2024-01-01",
        "first_payment_date": "2024-01-01",
        "required_end_date": "2029-01-01",
        "age_at_first_payment": "50.5",
        "account_balance_at_valuation": "250000",
        "initial_annual_payment_locked": "12000",
    }


def test_list_sepp_plans_empty(client: TestClient, scenario: dict) -> None:
    assert client.get(f"/scenarios/{scenario['id']}/sepp-plans").json() == []


def test_create_sepp_plan(client: TestClient, scenario_with_account: dict) -> None:
    sid = scenario_with_account["scenario"]["id"]
    aid = scenario_with_account["account"]["id"]
    resp = client.post(f"/scenarios/{sid}/sepp-plans", json=_sepp_payload(aid))
    assert resp.status_code == 201
    data = resp.json()
    assert data["method"] == "fixed_amortization"
    assert data["account_id"] == aid
    assert data["scenario_id"] == sid


def test_create_sepp_plan_invalid_account(client: TestClient, scenario: dict) -> None:
    resp = client.post(
        f"/scenarios/{scenario['id']}/sepp-plans",
        json=_sepp_payload("bad-account-id"),
    )
    assert resp.status_code == 400


def test_create_sepp_plan_scenario_not_found(client: TestClient) -> None:
    assert (
        client.post("/scenarios/bad-id/sepp-plans", json=_sepp_payload("aid")).status_code
        == 404
    )


def test_update_sepp_plan(client: TestClient, scenario_with_account: dict) -> None:
    sid = scenario_with_account["scenario"]["id"]
    aid = scenario_with_account["account"]["id"]
    plan_id = client.post(
        f"/scenarios/{sid}/sepp-plans", json=_sepp_payload(aid)
    ).json()["id"]
    updated = _sepp_payload(aid, status="completed")
    resp = client.put(f"/scenarios/{sid}/sepp-plans/{plan_id}", json=updated)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_update_sepp_plan_not_found(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    aid = scenario_with_account["account"]["id"]
    assert (
        client.put(
            f"/scenarios/{sid}/sepp-plans/bad-id", json=_sepp_payload(aid)
        ).status_code
        == 404
    )


def test_delete_sepp_plan(client: TestClient, scenario_with_account: dict) -> None:
    sid = scenario_with_account["scenario"]["id"]
    aid = scenario_with_account["account"]["id"]
    plan_id = client.post(
        f"/scenarios/{sid}/sepp-plans", json=_sepp_payload(aid)
    ).json()["id"]
    assert client.delete(f"/scenarios/{sid}/sepp-plans/{plan_id}").status_code == 204
    assert client.get(f"/scenarios/{sid}/sepp-plans").json() == []


def test_delete_sepp_plan_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.delete(
            f"/scenarios/{scenario['id']}/sepp-plans/bad-id"
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Roth conversion plan endpoints
# ---------------------------------------------------------------------------


def test_list_roth_conversions_empty(client: TestClient, scenario: dict) -> None:
    assert client.get(f"/scenarios/{scenario['id']}/roth-conversions").json() == []


def test_create_roth_conversion(client: TestClient, roth_accounts: dict) -> None:
    sid = roth_accounts["scenario"]["id"]
    resp = client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "20000",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == "20000"
    assert data["year"] == CURRENT_YEAR


def test_create_roth_conversion_with_tax_payment_source(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    resp = client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "20000",
            "tax_payment_source_account_id": roth_accounts["cash_id"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["tax_payment_source_account_id"] == roth_accounts["cash_id"]


def test_create_roth_conversion_invalid_source(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    assert (
        client.post(
            f"/scenarios/{sid}/roth-conversions",
            json={
                "source_account_id": "bad-id",
                "destination_account_id": roth_accounts["roth_id"],
                "year": CURRENT_YEAR,
                "amount": "20000",
            },
        ).status_code
        == 400
    )


def test_create_roth_conversion_invalid_destination(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    assert (
        client.post(
            f"/scenarios/{sid}/roth-conversions",
            json={
                "source_account_id": roth_accounts["trad_id"],
                "destination_account_id": "bad-id",
                "year": CURRENT_YEAR,
                "amount": "20000",
            },
        ).status_code
        == 400
    )


def test_create_roth_conversion_invalid_tax_source(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    assert (
        client.post(
            f"/scenarios/{sid}/roth-conversions",
            json={
                "source_account_id": roth_accounts["trad_id"],
                "destination_account_id": roth_accounts["roth_id"],
                "year": CURRENT_YEAR,
                "amount": "20000",
                "tax_payment_source_account_id": "bad-id",
            },
        ).status_code
        == 400
    )


def test_update_roth_conversion(client: TestClient, roth_accounts: dict) -> None:
    sid = roth_accounts["scenario"]["id"]
    plan_id = client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "20000",
        },
    ).json()["id"]
    resp = client.put(
        f"/scenarios/{sid}/roth-conversions/{plan_id}",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR + 1,
            "amount": "30000",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == "30000"
    assert resp.json()["year"] == CURRENT_YEAR + 1


def test_update_roth_conversion_not_found(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    assert (
        client.put(
            f"/scenarios/{sid}/roth-conversions/bad-id",
            json={
                "source_account_id": roth_accounts["trad_id"],
                "destination_account_id": roth_accounts["roth_id"],
                "year": CURRENT_YEAR,
                "amount": "20000",
            },
        ).status_code
        == 404
    )


def test_delete_roth_conversion(client: TestClient, roth_accounts: dict) -> None:
    sid = roth_accounts["scenario"]["id"]
    plan_id = client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "20000",
        },
    ).json()["id"]
    assert client.delete(f"/scenarios/{sid}/roth-conversions/{plan_id}").status_code == 204
    assert client.get(f"/scenarios/{sid}/roth-conversions").json() == []


def test_delete_roth_conversion_not_found(client: TestClient, scenario: dict) -> None:
    assert (
        client.delete(
            f"/scenarios/{scenario['id']}/roth-conversions/bad-id"
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Projection endpoints
# ---------------------------------------------------------------------------


def test_get_projection_not_found(client: TestClient, scenario: dict) -> None:
    assert client.get(f"/scenarios/{scenario['id']}/projection").status_code == 404


def test_run_projection_scenario_not_found(client: TestClient) -> None:
    assert client.post("/scenarios/bad-id/run-projection").status_code == 404


def test_run_projection_basic(client: TestClient, scenario_with_account: dict) -> None:
    sid = scenario_with_account["scenario"]["id"]
    client.put(
        f"/scenarios/{sid}/assumptions",
        json={
            "cpi_rate": "0.025",
            "healthcare_inflation_rate": "0.04",
            "ss_cola_rate": "0.025",
            "pension_cola_rate": "0",
            "bracket_indexing_rate": "0.025",
            "cash_reserve_target_months": 24,
            "irs_data_version": "2024-33",
            "engine_version": "api-test",
            "state": "MA",
            "tax_iteration_max": 5,
            "tax_iteration_tolerance": "1.00",
        },
    )
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    data = resp.json()
    assert "metadata" in data
    assert len(data["years"]) > 0
    assert len(data["account_balances"]) > 0
    assert data["metadata"]["engine_version"] == "api-test"


def test_run_projection_years_span(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    years = [y["year"] for y in resp.json()["years"]]
    # DOB 1975, life_expectancy_age 85 â†’ end_year 2060
    assert min(years) == CURRENT_YEAR
    assert max(years) == 1975 + 85


def test_run_projection_clears_previous_run(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    id1 = client.post(f"/scenarios/{sid}/run-projection").json()["metadata"]["id"]
    id2 = client.post(f"/scenarios/{sid}/run-projection").json()["metadata"]["id"]
    assert id1 != id2
    # GET returns the most recent
    assert client.get(f"/scenarios/{sid}/projection").json()["metadata"]["id"] == id2


def test_get_projection_after_run(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    run_id = client.post(f"/scenarios/{sid}/run-projection").json()["metadata"]["id"]
    assert client.get(f"/scenarios/{sid}/projection").json()["metadata"]["id"] == run_id


def test_run_projection_income_and_expense_reflected(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "100000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    )
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={
            "name": "Living",
            "kind": "must_spend",
            "annual_amount": "60000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    )
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    year0 = resp.json()["years"][0]
    assert Decimal(year0["gross_income"]) == Decimal("100000")
    assert Decimal(year0["expenses"]) == Decimal("60000")


def test_run_projection_with_roth_accounts(
    client: TestClient, roth_accounts: dict
) -> None:
    """Exercises account_to_engine_state for Roth accounts with roth_basis."""
    sid = roth_accounts["scenario"]["id"]
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    account_ids = {b["account_id"] for b in resp.json()["account_balances"]}
    assert roth_accounts["roth_id"] in account_ids
    assert roth_accounts["trad_id"] in account_ids


def test_run_projection_with_roth_conversion_plan(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "10000",
        },
    )
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    year0 = resp.json()["years"][0]
    assert Decimal(year0["roth_conversions"]) >= Decimal("0")


def test_projection_account_balances_have_correct_fields(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    for bal in resp.json()["account_balances"]:
        assert "beginning_balance" in bal
        assert "ending_balance" in bal
        assert "contributions" in bal
        assert "distributions" in bal
        assert "investment_return" in bal


# ---------------------------------------------------------------------------
# Delete endpoints
# ---------------------------------------------------------------------------


def test_delete_scenario(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    resp = client.delete(f"/scenarios/{sid}")
    assert resp.status_code == 204
    assert client.get(f"/scenarios/{sid}").status_code == 404


def test_delete_scenario_not_found(client: TestClient) -> None:
    assert client.delete("/scenarios/nonexistent").status_code == 404


def test_delete_scenario_cascades_projection_data(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    assert len(run_resp.json()["years"]) > 0
    resp = client.delete(f"/scenarios/{sid}")
    assert resp.status_code == 204
    assert client.get(f"/scenarios/{sid}").status_code == 404


def test_delete_scenario_cascades_assumptions_and_strategy(
    client: TestClient, scenario: dict
) -> None:
    sid = scenario["id"]
    client.put(f"/scenarios/{sid}/assumptions", json={"cpi_rate": "0.03"})
    resp = client.delete(f"/scenarios/{sid}")
    assert resp.status_code == 204


def test_delete_household(client: TestClient, scenario: dict) -> None:
    hid = scenario["household"]["id"]
    sid = scenario["id"]
    resp = client.delete(f"/households/{hid}")
    assert resp.status_code == 204
    assert client.get(f"/scenarios/{sid}").status_code == 404
    client.get("/households").json() if hasattr(client.get("/households"), "json") else []
    scenario_list = client.get("/scenarios").json()
    assert all(s["id"] != sid for s in scenario_list)


def test_delete_household_not_found(client: TestClient) -> None:
    assert client.delete("/households/nonexistent").status_code == 404


def test_delete_household_cascades_accounts_and_streams(
    client: TestClient, scenario_with_account: dict
) -> None:
    scenario = scenario_with_account["scenario"]
    hid = scenario["household"]["id"]
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "person_id": person_id,
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "100000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
            "is_taxable_federal": True,
            "is_taxable_state": True,
        },
    )
    resp = client.delete(f"/households/{hid}")
    assert resp.status_code == 204
    assert client.get(f"/scenarios/{sid}").status_code == 404


# ---------------------------------------------------------------------------
# Pydantic 422 validation
# ---------------------------------------------------------------------------


def test_create_household_invalid_filing_status(client: TestClient) -> None:
    resp = client.post(
        "/households",
        json={
            "name": "Test",
            "filing_status": "invalid_status",
            "state": "MA",
            "primary_person": {"name": "Jordan", "dob": "1975-04-15"},
            "scenario_name": "Baseline",
        },
    )
    assert resp.status_code == 422


def test_create_household_empty_name(client: TestClient, household_payload: dict) -> None:
    payload = {**household_payload, "name": ""}
    assert client.post("/households", json=payload).status_code == 422


def test_create_account_invalid_type(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Acct",
            "account_type": "not_a_real_type",
            "current_balance": "10000",
            "expected_return": "0.05",
        },
    )
    assert resp.status_code == 422


def test_create_income_invalid_kind(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/income-streams",
        json={
            "person_id": person_id,
            "name": "Income",
            "kind": "lottery_winnings",
            "annual_amount": "50000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "cpi",
            "is_taxable_federal": True,
            "is_taxable_state": True,
        },
    )
    assert resp.status_code == 422


def test_create_income_invalid_inflation_kind(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/income-streams",
        json={
            "person_id": person_id,
            "name": "Income",
            "kind": "salary",
            "annual_amount": "50000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "crypto_inflation",
            "is_taxable_federal": True,
            "is_taxable_state": True,
        },
    )
    assert resp.status_code == 422


def test_create_expense_invalid_kind(client: TestClient, scenario: dict) -> None:
    resp = client.post(
        f"/scenarios/{scenario['id']}/expense-streams",
        json={
            "name": "Misc",
            "kind": "luxury_yacht",
            "annual_amount": "5000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "cpi",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# All account types
# ---------------------------------------------------------------------------


def test_create_account_traditional_ira(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Trad IRA",
            "account_type": "traditional_ira",
            "current_balance": "150000",
            "expected_return": "0.07",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "traditional_ira"


def test_create_account_traditional_401k(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "401k",
            "account_type": "traditional_401k",
            "current_balance": "200000",
            "expected_return": "0.07",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "traditional_401k"


def test_create_account_traditional_403b(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "403b",
            "account_type": "traditional_403b",
            "current_balance": "80000",
            "expected_return": "0.06",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "traditional_403b"


def test_create_account_roth_401k(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Roth 401k",
            "account_type": "roth_401k",
            "current_balance": "50000",
            "expected_return": "0.07",
            "roth_first_contribution_year": 2010,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "roth_401k"


def test_create_account_roth_401k_requires_contribution_year(
    client: TestClient, scenario: dict
) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Roth 401k",
            "account_type": "roth_401k",
            "current_balance": "50000",
            "expected_return": "0.07",
        },
    )
    assert resp.status_code == 400


def test_create_account_hsa(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "HSA",
            "account_type": "hsa",
            "current_balance": "15000",
            "expected_return": "0.04",
            "hsa_qualified_medical_expense_pct": "0.8",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "hsa"


def test_create_account_governmental_457b(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "457b",
            "account_type": "governmental_457b",
            "current_balance": "120000",
            "expected_return": "0.06",
            "is_governmental_457b": True,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "governmental_457b"


def test_create_account_real_estate(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Primary Home",
            "account_type": "real_estate",
            "current_balance": "450000",
            "expected_return": "0.03",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["account_type"] == "real_estate"


def test_create_account_debt_negative_balance(client: TestClient, scenario: dict) -> None:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Mortgage",
            "account_type": "debt",
            "current_balance": "-250000",
            "expected_return": "0.04",
        },
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["current_balance"]) < 0


# ---------------------------------------------------------------------------
# Account update validation
# ---------------------------------------------------------------------------


def test_update_account_invalid_owner(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    account_id = scenario_with_account["account"]["id"]
    resp = client.put(
        f"/scenarios/{sid}/accounts/{account_id}",
        json={
            "owner_person_id": "nonexistent-person",
            "name": "Updated",
            "account_type": "cash",
            "current_balance": "100",
            "expected_return": "0",
        },
    )
    assert resp.status_code == 400


def test_update_account_cross_household(
    client: TestClient, household_payload: dict
) -> None:
    hh_a = client.post("/households", json=household_payload).json()
    hh_b = client.post(
        "/households", json={**household_payload, "name": "Household B"}
    ).json()
    person_b = hh_b["household"]["people"][0]["id"]
    acct_b = client.post(
        f"/scenarios/{hh_b['id']}/accounts",
        json={
            "owner_person_id": person_b,
            "name": "Acct",
            "account_type": "cash",
            "current_balance": "5000",
            "expected_return": "0",
        },
    ).json()
    resp = client.put(
        f"/scenarios/{hh_a['id']}/accounts/{acct_b['id']}",
        json={
            "owner_person_id": hh_a["household"]["people"][0]["id"],
            "name": "Updated",
            "account_type": "cash",
            "current_balance": "5000",
            "expected_return": "0",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# SEPP extended coverage
# ---------------------------------------------------------------------------


def test_list_sepp_plans_after_create(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    account_id = scenario_with_account["account"]["id"]
    client.post(
        f"/scenarios/{sid}/sepp-plans",
        json={
            "account_id": account_id,
            "method": "fixed_amortization",
            "valuation_date": f"{CURRENT_YEAR}-01-01",
            "first_payment_date": f"{CURRENT_YEAR}-01-01",
            "required_end_date": f"{CURRENT_YEAR + 5}-01-01",
            "age_at_first_payment": "50",
            "account_balance_at_valuation": "200000",
        },
    )
    resp = client.get(f"/scenarios/{sid}/sepp-plans")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_sepp_plan_scenario_not_found(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    account_id = scenario_with_account["account"]["id"]
    plan = client.post(
        f"/scenarios/{sid}/sepp-plans",
        json={
            "account_id": account_id,
            "method": "fixed_amortization",
            "valuation_date": f"{CURRENT_YEAR}-01-01",
            "first_payment_date": f"{CURRENT_YEAR}-01-01",
            "required_end_date": f"{CURRENT_YEAR + 5}-01-01",
            "age_at_first_payment": "50",
            "account_balance_at_valuation": "200000",
        },
    ).json()
    resp = client.put(
        f"/scenarios/nonexistent/sepp-plans/{plan['id']}",
        json={
            "account_id": account_id,
            "method": "rmd",
            "valuation_date": f"{CURRENT_YEAR}-01-01",
            "first_payment_date": f"{CURRENT_YEAR}-01-01",
            "required_end_date": f"{CURRENT_YEAR + 5}-01-01",
            "age_at_first_payment": "50",
            "account_balance_at_valuation": "200000",
        },
    )
    assert resp.status_code == 404


def test_create_sepp_plan_cross_household_account(
    client: TestClient, household_payload: dict
) -> None:
    hh_a = client.post("/households", json=household_payload).json()
    hh_b = client.post(
        "/households", json={**household_payload, "name": "Household B"}
    ).json()
    person_b = hh_b["household"]["people"][0]["id"]
    acct_b = client.post(
        f"/scenarios/{hh_b['id']}/accounts",
        json={
            "owner_person_id": person_b,
            "name": "Acct",
            "account_type": "traditional_ira",
            "current_balance": "100000",
            "expected_return": "0.06",
        },
    ).json()
    resp = client.post(
        f"/scenarios/{hh_a['id']}/sepp-plans",
        json={
            "account_id": acct_b["id"],
            "method": "rmd",
            "valuation_date": f"{CURRENT_YEAR}-01-01",
            "first_payment_date": f"{CURRENT_YEAR}-01-01",
            "required_end_date": f"{CURRENT_YEAR + 5}-01-01",
            "age_at_first_payment": "55",
            "account_balance_at_valuation": "100000",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Roth conversion extended coverage
# ---------------------------------------------------------------------------


def test_list_roth_conversions_after_create(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "5000",
        },
    )
    resp = client.get(f"/scenarios/{sid}/roth-conversions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_roth_conversion_scenario_not_found(
    client: TestClient, roth_accounts: dict
) -> None:
    sid = roth_accounts["scenario"]["id"]
    plan = client.post(
        f"/scenarios/{sid}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "5000",
        },
    ).json()
    resp = client.put(
        f"/scenarios/nonexistent/roth-conversions/{plan['id']}",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "10000",
        },
    )
    assert resp.status_code == 404


def test_create_roth_conversion_cross_household_source(
    client: TestClient, household_payload: dict, roth_accounts: dict
) -> None:
    hh_b = client.post(
        "/households", json={**household_payload, "name": "Other HH"}
    ).json()
    resp = client.post(
        f"/scenarios/{hh_b['id']}/roth-conversions",
        json={
            "source_account_id": roth_accounts["trad_id"],
            "destination_account_id": roth_accounts["roth_id"],
            "year": CURRENT_YEAR,
            "amount": "5000",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Projection extended coverage
# ---------------------------------------------------------------------------


def test_run_projection_metadata_fields(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    meta = resp.json()["metadata"]
    assert "run_at" in meta
    assert "engine_version" in meta
    assert "irs_data_version" in meta
    assert "assumption_snapshot_json" in meta


def test_run_projection_returns_warnings_field(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    assert isinstance(resp.json()["warnings"], list)


def test_run_projection_with_expense_stream(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={
            "name": "Living Expenses",
            "kind": "must_spend",
            "annual_amount": "48000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "cpi",
        },
    )
    resp = client.post(f"/scenarios/{sid}/run-projection")
    assert resp.status_code == 200
    assert Decimal(resp.json()["years"][0]["expenses"]) > Decimal("0")


def test_run_projection_mfj_household(client: TestClient) -> None:
    resp = client.post(
        "/households",
        json={
            "name": "Married Couple",
            "filing_status": "mfj",
            "state": "MA",
            "primary_person": {
                "name": "Alex",
                "dob": "1968-06-01",
                "life_expectancy_age": 80,
            },
            "scenario_name": "Joint Baseline",
        },
    )
    assert resp.status_code == 201
    sid = resp.json()["id"]
    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    assert len(run_resp.json()["years"]) > 0


def test_get_projection_matches_run_result(
    client: TestClient, scenario_with_account: dict
) -> None:
    sid = scenario_with_account["scenario"]["id"]
    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    get_resp = client.get(f"/scenarios/{sid}/projection")
    assert get_resp.status_code == 200
    assert run_resp.json()["metadata"]["id"] == get_resp.json()["metadata"]["id"]
    assert len(run_resp.json()["years"]) == len(get_resp.json()["years"])


# ---------------------------------------------------------------------------
# Income/expense stream list after create
# ---------------------------------------------------------------------------


def test_list_income_streams_after_create(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "person_id": person_id,
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "90000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
            "is_taxable_federal": True,
            "is_taxable_state": True,
        },
    )
    resp = client.get(f"/scenarios/{sid}/income-streams")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_expense_streams_after_create(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={
            "name": "Rent",
            "kind": "must_spend",
            "annual_amount": "24000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "cpi",
        },
    )
    resp = client.get(f"/scenarios/{sid}/expense-streams")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Withdrawal strategy persistence
# ---------------------------------------------------------------------------


def test_update_withdrawal_strategy_persists(client: TestClient, scenario: dict) -> None:
    import json as _json

    sid = scenario["id"]
    new_order = ["roth_ira", "cash", "taxable_brokerage"]
    client.put(
        f"/scenarios/{sid}/withdrawal-strategy",
        json={"order_json": _json.dumps(new_order), "surplus_target": "cash"},
    )
    resp = client.get(f"/scenarios/{sid}/withdrawal-strategy")
    assert resp.status_code == 200
    assert _json.loads(resp.json()["order_json"]) == new_order
    assert resp.json()["surplus_target"] == "cash"


# ---------------------------------------------------------------------------
# Cross-resource consistency
# ---------------------------------------------------------------------------


def test_list_households_returns_all_created(
    client: TestClient, household_payload: dict
) -> None:
    client.post("/households", json=household_payload)
    client.post("/households", json={**household_payload, "name": "Second Family"})
    resp = client.get("/households")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_scenario_detail_total_balance_sums_accounts(
    client: TestClient, scenario: dict
) -> None:
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    for name, balance in [("Cash", "10000"), ("IRA", "90000")]:
        client.post(
            f"/scenarios/{sid}/accounts",
            json={
                "owner_person_id": person_id,
                "name": name,
                "account_type": "cash",
                "current_balance": balance,
                "expected_return": "0",
            },
        )
    resp = client.get(f"/scenarios/{sid}")
    assert resp.status_code == 200
    assert Decimal(resp.json()["total_account_balance"]) == Decimal("100000")


# ---------------------------------------------------------------------------
# SEPP projection integration — guards Bug #1 (null initial_annual_payment_locked).
# ---------------------------------------------------------------------------


def _make_sepp_scenario(client: TestClient) -> dict:
    """Create a household with life_expectancy_age=80 to stay within the uniform
    lifetime table coverage during projection.
    """
    resp = client.post(
        "/households",
        json={
            "name": "SEPP Test HH",
            "filing_status": "single",
            "state": "MA",
            "primary_person": {
                "name": "Sam",
                "dob": "1975-04-15",
                "life_expectancy_age": 80,
            },
            "scenario_name": "SEPP Scenario",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _make_sepp_account(client: TestClient, scenario: dict, balance: str = "300000") -> dict:
    person_id = scenario["household"]["people"][0]["id"]
    resp = client.post(
        f"/scenarios/{scenario['id']}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Trad IRA for SEPP",
            "account_type": "traditional_ira",
            "current_balance": balance,
            "expected_return": "0",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_run_projection_sepp_with_null_locked_payment_computes_payment(
    client: TestClient,
) -> None:
    """Bug #1 guard: when initial_annual_payment_locked is null, the engine must
    compute the annual payment via calculate_initial_payment, NOT default to $0.
    """
    scenario = _make_sepp_scenario(client)
    sid = scenario["id"]
    # Person dob 1975-04-15 → age 48 at first_payment_date 2024-01-01.
    # Single life factor at 48 = 38.2 → expected RMD-method payment = 300000 / 38.2 ≈ 7853.40.
    ira = _make_sepp_account(client, scenario, balance="300000")
    sepp_resp = client.post(
        f"/scenarios/{sid}/sepp-plans",
        json={
            "account_id": ira["id"],
            "method": "rmd",
            "status": "active",
            "valuation_date": "2024-01-01",
            "first_payment_date": "2024-01-01",
            "required_end_date": "2034-12-31",
            "age_at_first_payment": "48",
            "account_balance_at_valuation": "300000",
            # Critical: omit initial_annual_payment_locked entirely.
        },
    )
    assert sepp_resp.status_code == 201
    assert sepp_resp.json().get("initial_annual_payment_locked") is None

    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    year0 = run_resp.json()["years"][0]
    expected = (Decimal("300000") / Decimal("38.2")).quantize(Decimal("0.01"))
    # Required distributions in year 0 should equal the computed SEPP payment
    # (no RMD because person age 48 < 73), NOT $0 (the bug).
    assert Decimal(year0["required_distributions"]) == expected
    assert Decimal(year0["required_distributions"]) > Decimal("0")


def test_run_projection_sepp_with_locked_payment_uses_locked_value(
    client: TestClient,
) -> None:
    """When initial_annual_payment_locked is set, the engine uses it as-is."""
    scenario = _make_sepp_scenario(client)
    sid = scenario["id"]
    ira = _make_sepp_account(client, scenario, balance="300000")
    locked_value = "8000"
    sepp_resp = client.post(
        f"/scenarios/{sid}/sepp-plans",
        json={
            "account_id": ira["id"],
            "method": "rmd",
            "status": "active",
            "valuation_date": "2024-01-01",
            "first_payment_date": "2024-01-01",
            "required_end_date": "2034-12-31",
            "age_at_first_payment": "48",
            "account_balance_at_valuation": "300000",
            "initial_annual_payment_locked": locked_value,
        },
    )
    assert sepp_resp.status_code == 201

    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    year0 = run_resp.json()["years"][0]
    assert Decimal(year0["required_distributions"]) == Decimal("8000.00")


def test_run_projection_sepp_shortfall_withdrawn_from_non_sepp_accounts(
    client: TestClient,
) -> None:
    """Expenses exceeding SEPP payment must be funded from non-SEPP accounts."""
    scenario = _make_sepp_scenario(client)
    sid = scenario["id"]
    ira = _make_sepp_account(client, scenario, balance="300000")
    # Cash account to fund the shortfall
    person_id = scenario["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Cash",
            "account_type": "cash",
            "current_balance": "100000",
            "expected_return": "0",
        },
    )
    client.post(
        f"/scenarios/{sid}/sepp-plans",
        json={
            "account_id": ira["id"],
            "method": "rmd",
            "status": "active",
            "valuation_date": "2024-01-01",
            "first_payment_date": "2024-01-01",
            "required_end_date": "2034-12-31",
            "age_at_first_payment": "48",
            "account_balance_at_valuation": "300000",
            "initial_annual_payment_locked": "5000",
        },
    )
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={
            "name": "Living",
            "kind": "must_spend",
            "annual_amount": "20000",
            "start_year": CURRENT_YEAR,
            "inflation_kind": "none",
        },
    )
    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    data = run_resp.json()
    year0 = data["years"][0]
    assert Decimal(year0["required_distributions"]) == Decimal("5000.00")
    # Gap = 20000 - 5000 = 15000 must come from flex withdrawals.
    assert Decimal(year0["flexible_withdrawals"]) >= Decimal("15000.00")
    # Verify the IRA was NOT touched by flex (only its SEPP $5000 was distributed).
    ira_balance = next(
        b for b in data["account_balances"]
        if b["account_id"] == ira["id"] and b["year"] == year0["year"]
    )
    assert Decimal(ira_balance["distributions"]) == Decimal("5000.00")


def test_run_projection_active_sepp_decrements_account_balance_each_year(
    client: TestClient,
) -> None:
    """Active SEPP plan: account balance must decrease each year by annual_payment."""
    scenario = _make_sepp_scenario(client)
    sid = scenario["id"]
    ira = _make_sepp_account(client, scenario, balance="300000")
    annual_payment = Decimal("10000")
    client.post(
        f"/scenarios/{sid}/sepp-plans",
        json={
            "account_id": ira["id"],
            "method": "rmd",
            "status": "active",
            "valuation_date": "2024-01-01",
            "first_payment_date": "2024-01-01",
            "required_end_date": f"{CURRENT_YEAR + 6}-12-31",
            "age_at_first_payment": "48",
            "account_balance_at_valuation": "300000",
            "initial_annual_payment_locked": str(annual_payment),
        },
    )
    run_resp = client.post(f"/scenarios/{sid}/run-projection")
    assert run_resp.status_code == 200
    data = run_resp.json()
    ira_rows = sorted(
        [b for b in data["account_balances"] if b["account_id"] == ira["id"]],
        key=lambda r: r["year"],
    )
    # While SEPP is active (CURRENT_YEAR..CURRENT_YEAR+6), each year's distributions == 10000.
    active_rows = [r for r in ira_rows if r["year"] <= CURRENT_YEAR + 6]
    assert len(active_rows) >= 2
    for row in active_rows:
        assert Decimal(row["distributions"]) == Decimal("10000.00")
    # And ending balance must monotonically decrease (expected_return=0 and no contributions).
    for prev, curr in zip(active_rows, active_rows[1:], strict=False):
        assert Decimal(curr["ending_balance"]) < Decimal(prev["ending_balance"])


def test_delete_account_reduces_balance(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    acct = client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Temp",
            "account_type": "cash",
            "current_balance": "5000",
            "expected_return": "0",
        },
    ).json()
    client.delete(f"/scenarios/{sid}/accounts/{acct['id']}")
    detail = client.get(f"/scenarios/{sid}").json()
    assert Decimal(detail["total_account_balance"]) == Decimal("0")



# ---------------------------------------------------------------------------
# Contributions (accumulation-phase savings + employer match)
# ---------------------------------------------------------------------------


def _make_account(client: TestClient, sid: str, person_id: str, acct_type: str) -> str:
    extra: dict = {}
    if acct_type in {"roth_ira", "roth_401k"}:
        extra["roth_first_contribution_year"] = 2015
    resp = client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": acct_type,
            "account_type": acct_type,
            "current_balance": "0",
            "expected_return": "0",
            **extra,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_contribution_crud(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    acct_id = _make_account(client, sid, person_id, "traditional_401k")

    assert client.get(f"/scenarios/{sid}/contributions").json() == []

    created = client.post(
        f"/scenarios/{sid}/contributions",
        json={
            "account_id": acct_id,
            "annual_amount": "20000",
            "start_year": 2024,
            "end_year": 2030,
            "inflation_kind": "cpi",
            "employer_match_amount": "5000",
        },
    )
    assert created.status_code == 201
    cid = created.json()["id"]
    assert Decimal(created.json()["employer_match_amount"]) == Decimal("5000")

    listed = client.get(f"/scenarios/{sid}/contributions").json()
    assert len(listed) == 1

    updated = client.put(
        f"/scenarios/{sid}/contributions/{cid}",
        json={
            "account_id": acct_id,
            "annual_amount": "25000",
            "start_year": 2024,
            "inflation_kind": "none",
            "employer_match_amount": "0",
        },
    )
    assert updated.status_code == 200
    assert Decimal(updated.json()["annual_amount"]) == Decimal("25000")

    assert client.delete(f"/scenarios/{sid}/contributions/{cid}").status_code == 204
    assert client.get(f"/scenarios/{sid}/contributions").json() == []


def test_contribution_feeds_projection(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    cash_id = _make_account(client, sid, person_id, "cash")
    k_id = _make_account(client, sid, person_id, "traditional_401k")
    # Fund cash so the household has income via... use a salary income stream instead.
    client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "100000",
            "start_year": 2024,
            "inflation_kind": "none",
        },
    )
    client.post(
        f"/scenarios/{sid}/contributions",
        json={
            "account_id": k_id,
            "annual_amount": "18000",
            "start_year": 2024,
            "inflation_kind": "none",
            "employer_match_amount": "9000",
        },
    )
    run = client.post(f"/scenarios/{sid}/run-projection")
    assert run.status_code == 200
    balances = run.json()["account_balances"]
    first_year = min(b["year"] for b in balances)
    k_bal = next(
        b for b in balances if b["account_id"] == k_id and b["year"] == first_year
    )
    # 18k employee + 9k employer match contributed in the first year.
    assert Decimal(k_bal["contributions"]) == Decimal("27000.00")
    assert cash_id  # cash account exists for surplus routing


def test_monte_carlo_endpoint(client: TestClient, scenario: dict) -> None:
    sid = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Brokerage",
            "account_type": "taxable_brokerage",
            "current_balance": "1000000",
            "expected_return": "0.06",
            "return_stddev": "0.10",
            "cost_basis_pct": "0.8",
        },
    )
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={"name": "Living", "kind": "must_spend", "annual_amount": "40000", "start_year": 2024},
    )
    resp = client.post(f"/scenarios/{sid}/monte-carlo?trials=60")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trials"] == 60
    assert 0 <= float(body["chance_of_success"]) <= 100


def test_rate_variant_optimistic_beats_pessimistic() -> None:
    from app.main import apply_rate_variant
    from planner_engine.common import AccountYearState, Person
    from planner_engine.projection import (
        AssumptionSet,
        ExpenseStream,
        ScenarioInput,
        run_projection,
    )

    base = ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2034,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1959, age_by_year={y: y - 1959 for y in range(2024, 2035)})],
        accounts=[
            AccountYearState(
                "brk", "p1", "taxable_brokerage", Decimal("1000000"), Decimal("0.06"),
                cost_basis_pct=Decimal("0.8"),
            )
        ],
        expense_streams=[
            ExpenseStream("e", "must_spend", Decimal("40000"), 2024, inflation_kind="none")
        ],
        assumptions=AssumptionSet(cpi_rate=Decimal("0.025")),
    )
    opt = run_projection(apply_rate_variant(base, "optimistic"), "2024-33", "test")
    pess = run_projection(apply_rate_variant(base, "pessimistic"), "2024-33", "test")
    avg = run_projection(apply_rate_variant(base, "average"), "2024-33", "test")
    assert opt.summary.estate_net_worth > avg.summary.estate_net_worth
    assert avg.summary.estate_net_worth > pess.summary.estate_net_worth


def test_roth_explorer_endpoint(client: TestClient) -> None:
    hh = client.post(
        "/households",
        json={
            "name": "Explorer HH",
            "filing_status": "single",
            "state": "MA",
            "primary_person": {"name": "Pat", "dob": "1962-01-01", "life_expectancy_age": 80},
            "scenario_name": "Base",
        },
    ).json()
    sid = hh["id"]
    pid = hh["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": pid, "name": "IRA", "account_type": "traditional_ira",
            "current_balance": "700000", "expected_return": "0.05",
        },
    )
    client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": pid, "name": "Roth", "account_type": "roth_ira",
            "current_balance": "0", "expected_return": "0.05",
            "roth_first_contribution_year": 2010,
        },
    )
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={"name": "Living", "kind": "must_spend", "annual_amount": "40000", "start_year": 2024},
    )
    resp = client.post(
        f"/scenarios/{sid}/roth-explorer?strategy=bracket&target_rate=0.22"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"] == "bracket"
    assert len(body["suggestions"]) > 0
    # Apply persists the suggested conversions.
    applied = client.post(
        f"/scenarios/{sid}/roth-explorer?strategy=bracket&target_rate=0.22&apply=true"
    ).json()
    plans = client.get(f"/scenarios/{sid}/roth-conversions").json()
    assert len(plans) == len(applied["suggestions"])


def test_social_security_explorer_endpoint(client: TestClient) -> None:
    hh = client.post(
        "/households",
        json={
            "name": "SS HH",
            "filing_status": "single",
            "state": "MA",
            "primary_person": {"name": "Sam", "dob": "1965-06-01", "life_expectancy_age": 90},
            "scenario_name": "Base",
        },
    ).json()
    sid = hh["id"]
    pid = hh["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/income-streams",
        json={
            "name": "SS", "kind": "social_security", "annual_amount": "21000",
            "start_year": 2027, "inflation_kind": "ss_cola", "person_id": pid,
            "claiming_age": 62,
        },
    )
    resp = client.get(f"/scenarios/{sid}/social-security-explorer?person_id={pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["options"]) == 9
    assert body["current_claiming_age"] == 62
    # PIA backed out from a 62 benefit of 21000 (0.70 multiplier) ≈ 30000.
    assert abs(float(body["pia_annual"]) - 30000) < 1
    assert body["max_lifetime_claiming_age"] == 70


def test_insights_endpoint(client: TestClient) -> None:
    hh = client.post(
        "/households",
        json={
            "name": "Insights HH",
            "filing_status": "single",
            "state": "MA",
            "primary_person": {"name": "Lee", "dob": "1958-01-01", "life_expectancy_age": 90},
            "scenario_name": "Base",
        },
    ).json()
    sid = hh["id"]
    pid = hh["household"]["people"][0]["id"]
    client.post(
        f"/scenarios/{sid}/accounts",
        json={
            "owner_person_id": pid, "name": "Brokerage", "account_type": "taxable_brokerage",
            "current_balance": "2000000", "expected_return": "0.05",
            "return_stddev": "0.10", "cost_basis_pct": "0.8",
        },
    )
    client.post(
        f"/scenarios/{sid}/expense-streams",
        json={"name": "Living", "kind": "must_spend", "annual_amount": "40000", "start_year": 2024},
    )
    resp = client.get(f"/scenarios/{sid}/insights")
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["score"] <= 100
    assert body["rating"] in {"Excellent", "Good", "Fair", "At Risk"}
    assert len(body["components"]) >= 3
