from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import app.models  # noqa: F401
from app.database import Base, get_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def client_with_database(tmp_path: Path) -> TestClient:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_phase7_end_to_end_projection_api(tmp_path: Path) -> None:
    client = client_with_database(tmp_path)
    current_year = datetime.now(UTC).year

    household_response = client.post(
        "/households",
        json={
            "name": "API Test",
            "filing_status": "single",
            "state": "MA",
            "primary_person": {
                "name": "Taylor",
                "dob": "1980-01-01",
                "life_expectancy_age": 81,
            },
            "scenario_name": "Baseline",
        },
    )
    assert household_response.status_code == 201
    scenario = household_response.json()
    scenario_id = scenario["id"]
    person_id = scenario["household"]["people"][0]["id"]

    account_response = client.post(
        f"/scenarios/{scenario_id}/accounts",
        json={
            "owner_person_id": person_id,
            "name": "Cash",
            "account_type": "cash",
            "current_balance": "50000",
            "expected_return": "0",
        },
    )
    assert account_response.status_code == 201
    assert client.get(f"/scenarios/{scenario_id}/accounts").status_code == 200

    income_response = client.post(
        f"/scenarios/{scenario_id}/income-streams",
        json={
            "person_id": person_id,
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "30000",
            "start_year": current_year,
            "inflation_kind": "none",
        },
    )
    assert income_response.status_code == 201
    income_id = income_response.json()["id"]

    update_income_response = client.put(
        f"/scenarios/{scenario_id}/income-streams/{income_id}",
        json={
            "person_id": person_id,
            "name": "Salary",
            "kind": "salary",
            "annual_amount": "32000",
            "start_year": current_year,
            "inflation_kind": "none",
        },
    )
    assert update_income_response.status_code == 200
    assert update_income_response.json()["annual_amount"] == "32000"

    expense_response = client.post(
        f"/scenarios/{scenario_id}/expense-streams",
        json={
            "name": "Living",
            "kind": "must_spend",
            "annual_amount": "20000",
            "start_year": current_year,
            "inflation_kind": "none",
        },
    )
    assert expense_response.status_code == 201

    assumptions_response = client.put(
        f"/scenarios/{scenario_id}/assumptions",
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
    assert assumptions_response.status_code == 200

    strategy_response = client.get(f"/scenarios/{scenario_id}/withdrawal-strategy")
    assert strategy_response.status_code == 200

    run_response = client.post(f"/scenarios/{scenario_id}/run-projection")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["metadata"]["engine_version"] == "api-test"
    assert len(run_payload["years"]) > 0
    assert len(run_payload["account_balances"]) > 0

    latest_response = client.get(f"/scenarios/{scenario_id}/projection")
    assert latest_response.status_code == 200
    assert latest_response.json()["metadata"]["id"] == run_payload["metadata"]["id"]

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    assert "/scenarios/{scenario_id}/run-projection" in openapi_response.json()["paths"]

    delete_income_response = client.delete(f"/scenarios/{scenario_id}/income-streams/{income_id}")
    assert delete_income_response.status_code == 204

    app.dependency_overrides.clear()
