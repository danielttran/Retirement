# Personal Retirement Planner

Local-first deterministic retirement projection engine. All arithmetic uses `Decimal` — no floating-point.

## Prerequisites

- Python 3.11+
- Node.js 20+

## Quickstart

### 1. Install Python dependencies

```powershell
pip install -e ".[dev]"
```

### 2. Start the API server

```powershell
cd apps/api
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 3. Start the web app

```powershell
cd apps/web
npm install
npm run dev
```

Web app available at `http://localhost:3000`.

### 4. Create your first projection

1. Open `http://localhost:3000`
2. Create a household with one or more people
3. Create a scenario and configure accounts, income streams, and expenses
4. Click **Run Projection** to generate a multi-year forecast
5. View charts and download CSV exports from the projection page
6. Delete a scenario or entire household from the scenario detail page (Danger zone section)

## Run tests

Double-click `runtest.bat` to run all tests automatically, or from a terminal:

```powershell
# All tests (255 tests, auto-discovers future test files)
python -m pytest tests\ -v --tb=short

# Coverage report
python -m pytest --cov=planner_engine --cov-report=term-missing

# Type check
python -m mypy

# Lint
python -m ruff check packages/planner_engine apps/api
```

Test files in `tests/`:

| File | What it covers |
|---|---|
| `test_api_comprehensive.py` | All REST endpoints — CRUD, projections, delete, cascades |
| `test_engine_tax.py` | Federal/state tax engine, LTCG brackets, SS taxation |
| `test_engine_rmd_roth_withdrawal.py` | RMD computation, Roth withdrawal rules, conversion engine |
| `test_engine_sepp.py` | SEPP/72(t) calculation methods |
| `test_engine_projection.py` | End-to-end projection scenarios |
| `test_engine_projection_internals.py` | Projection engine internals |
| `test_engine_properties.py` | Property-based tests (Hypothesis) |
| `test_db_and_irs_data.py` | Database models and IRS data lookups |
| `test_api_e2e.py` | Full API smoke test |

## Local Development

Reset the local SQLite database after model changes:

```powershell
npm run reset:db
```

## Project structure

```
packages/
  planner_engine/     # Pure Python projection engine (Decimal throughout)
    sepp/             # SEPP/72(t) calculator
    rmd/              # Required Minimum Distribution engine
    roth/             # Roth conversion engine
    tax/              # Federal + state tax engine
    withdrawal/       # Withdrawal sequencing
    projection/       # Scenario runner
  irs_data/           # IRS brackets, RMD tables (versioned by publication)
apps/
  api/                # FastAPI REST API
  web/                # Next.js frontend with Recharts
tests/                # pytest test suite
```

## Disclaimer

This tool provides estimates for personal planning purposes only. It is not financial, tax, or legal advice. Consult a qualified professional before making retirement decisions.
