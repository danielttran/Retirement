from __future__ import annotations

from planner_engine.tax.engine import (
    TaxableIncomeMA,
    TaxInput,
    TaxResult,
    apply_ltcg_brackets_stacked,
    apply_ordinary_brackets,
    compute_early_withdrawal_penalty,
    compute_provisional_income,
    compute_taxes,
    federal_tax,
    state_tax_ma,
    taxable_social_security,
)
from planner_engine.tax.medicare import (
    irmaa_annual_surcharge,
    irmaa_monthly_surcharge,
)

__all__ = [
    "TaxInput",
    "TaxResult",
    "TaxableIncomeMA",
    "apply_ltcg_brackets_stacked",
    "apply_ordinary_brackets",
    "compute_early_withdrawal_penalty",
    "compute_provisional_income",
    "compute_taxes",
    "federal_tax",
    "irmaa_annual_surcharge",
    "irmaa_monthly_surcharge",
    "state_tax_ma",
    "taxable_social_security",
]
