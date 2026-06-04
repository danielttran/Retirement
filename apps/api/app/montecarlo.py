"""Monte Carlo / chance-of-success driver (Boldin-style).

Lives outside ``planner_engine`` because it is inherently stochastic (floating-point sampling).
It perturbs per-account, per-year returns and per-trial inflation, then runs the deterministic,
Decimal-based projection engine once per trial and aggregates outcomes.

Success definition (matching Boldin's updated rule): a trial succeeds only if liquid savings never
deplete to zero in any modeled year.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, replace
from decimal import Decimal

from planner_engine.projection import ScenarioInput, run_projection

# Default annual return standard deviation by asset class when an account does not specify one.
_DEFAULT_STDDEV: dict[str, str] = {
    "taxable_brokerage": "0.12",
    "traditional_ira": "0.12",
    "traditional_401k": "0.12",
    "traditional_403b": "0.12",
    "governmental_457b": "0.12",
    "roth_ira": "0.12",
    "roth_401k": "0.12",
    "hsa": "0.10",
    "real_estate": "0.08",
    "cash": "0.01",
}
# Account types whose returns are randomized (cash/debt are held at their fixed rate).
_VOLATILE_TYPES = set(_DEFAULT_STDDEV) - {"cash"}
_RETURN_FLOOR = -0.60
_RETURN_CEIL = 0.60
_INFLATION_STDDEV = 0.01


@dataclass(frozen=True)
class MonteCarloResult:
    trials: int
    success_count: int
    chance_of_success: Decimal  # percent, 0..100, 1 decimal
    p10_estate: Decimal
    p50_estate: Decimal
    p90_estate: Decimal
    median_out_of_savings_age: int | None


def _percentile(sorted_values: list[Decimal], pct: float) -> Decimal:
    if not sorted_values:
        return Decimal("0")
    idx = int(round(pct * (len(sorted_values) - 1)))
    return sorted_values[idx]


def run_monte_carlo(
    scenario: ScenarioInput,
    irs_data_version: str,
    engine_version: str,
    trials: int = 500,
    seed: int | None = None,
) -> MonteCarloResult:
    rng = random.Random(seed)
    years = list(range(scenario.start_year, scenario.end_year + 1))
    volatile_accounts = [a for a in scenario.accounts if a.account_type in _VOLATILE_TYPES]

    successes = 0
    estates: list[Decimal] = []
    out_ages: list[int] = []

    for _ in range(trials):
        overrides: dict[str, dict[int, Decimal]] = {}
        for account in volatile_accounts:
            mu = float(account.expected_return)
            sigma_src = account.return_stddev
            sigma = (
                float(sigma_src)
                if sigma_src is not None and sigma_src > Decimal("0")
                else float(_DEFAULT_STDDEV.get(account.account_type, "0.10"))
            )
            year_map: dict[int, Decimal] = {}
            for year in years:
                drawn = max(_RETURN_FLOOR, min(_RETURN_CEIL, rng.gauss(mu, sigma)))
                year_map[year] = Decimal(str(round(drawn, 6)))
            overrides[account.id] = year_map

        cpi = max(0.0, rng.gauss(float(scenario.assumptions.cpi_rate), _INFLATION_STDDEV))
        trial_assumptions = replace(scenario.assumptions, cpi_rate=Decimal(str(round(cpi, 6))))
        trial_scenario = replace(
            scenario, assumptions=trial_assumptions, return_overrides=overrides
        )
        run = run_projection(trial_scenario, irs_data_version, engine_version)
        summary = run.summary
        estates.append(summary.estate_net_worth)
        if summary.out_of_savings_age is None:
            successes += 1
        else:
            out_ages.append(summary.out_of_savings_age)

    estates.sort()
    out_ages.sort()
    chance = (
        (Decimal(successes) / Decimal(trials) * Decimal("100")).quantize(Decimal("0.1"))
        if trials
        else Decimal("0")
    )
    median_out = out_ages[len(out_ages) // 2] if out_ages else None
    return MonteCarloResult(
        trials=trials,
        success_count=successes,
        chance_of_success=chance,
        p10_estate=_percentile(estates, 0.10),
        p50_estate=_percentile(estates, 0.50),
        p90_estate=_percentile(estates, 0.90),
        median_out_of_savings_age=median_out,
    )
