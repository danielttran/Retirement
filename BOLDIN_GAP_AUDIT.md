# Boldin Feature-Parity Gap Audit

Living checklist auditing this Personal Retirement Planner against **Boldin** (formerly
NewRetirement). Goal: close all *relevant* gaps with identical/similar usage. Single-user
personal use is assumed, so inherently multi-user / external-service / hosted-only features
are **out of scope** (see bottom).

Status legend: ✅ done · 🟡 partial · ❌ missing · ⛔ out of scope (single-user/local)

---

## 1. Profile / Household
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Single or couple, per-person ages | ✓ | ✓ | ✅ |
| Life expectancy / longevity per person | ✓ | ✓ | ✅ |
| Retirement age/date per person | ✓ | ✓ | ✅ |
| Filing status, state of residence | ✓ | ✓ | ✅ |
| Death-of-spouse transition (filing→single, SS survivor) | ✓ | ❌ | ❌ |

## 2. Income
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Salary, part-time, bonus | ✓ | ✓ (salary) | ✅ |
| Pension w/ COLA + survivor option | ✓ | 🟡 (COLA, no survivor %) | 🟡 |
| Social Security w/ claiming age | ✓ | ✓ | ✅ |
| SS spousal + survivor benefit | ✓ | ❌ | ❌ |
| Annuity (incl. deferred/future-purchase) | ✓ | 🟡 (basic) | 🟡 |
| Rental / passive income | ✓ | ✓ (passive) | ✅ |
| Windfall / one-time income | ✓ | ❌ | ❌ |

## 3. Expenses
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Categorized budget | ✓ | 🟡 (named streams) | 🟡 |
| Must-have vs nice-to-have | ✓ | ✓ (must/discretionary) | ✅ |
| Healthcare w/ separate inflation | ✓ | ✓ | ✅ |
| One-time / planned expenses | ✓ | ✓ (one_time) | ✅ |
| Spending phases / "smile" | ✓ | 🟡 (via streams) | 🟡 |
| Long-term care modeling | ✓ | ❌ | ❌ |

## 4. Accounts / Assets
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Cash, brokerage, Trad/Roth IRA/401k/403b, HSA, 457b | ✓ | ✓ | ✅ |
| Real estate / primary home | ✓ | 🟡 (balance+appr.) | 🟡 |
| **Contributions + employer match** | ✓ | ✓ | ✅ |
| Per-account rate of return | ✓ | ✓ | ✅ |
| Account exclusion from auto-withdrawal/RMD/conv | ✓ | 🟡 (withdrawals) | 🟡 |
| Home sale / downsize event | ✓ | ❌ | ❌ |
| 529, deferred comp, life insurance (extra types) | ✓ | ❌ | ❌ |

## 5. Debt
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Mortgage / loan w/ amortization + payoff | ✓ | ✓ (payment + interest + payoff) | ✅ |
| Reverse mortgage / HELOC | ✓ | ❌ | ⛔? (advanced) |

## 6. Withdrawal Strategy
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Customizable drawdown order | ✓ | ✓ | ✅ |
| Roth 3-layer + HSA rules | ✓ | ✓ | ✅ |
| RMDs | ✓ | ✓ | ✅ |
| Rate-of-return-ordered depletion within bucket | ✓ | ❌ | ❌ |
| Manual scheduled transfers ("Money Flows") | ✓ | ❌ | ❌ |

## 7. Roth Conversion Explorer
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Manual conversion schedule | ✓ | ✓ | ✅ |
| Bracket-fill optimizer | ✓ | ✓ | ✅ |
| IRMAA-limit optimizer | ✓ | ✓ | ✅ |
| Lowest-lifetime-tax / highest-estate optimizer | ✓ | 🟡 (compares lifetime tax + estate) | 🟡 |

## 8. Tax Planning
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Federal + state, year-by-year | ✓ | ✓ (MA) | ✅ |
| LTCG stacking | ✓ | ✓ | ✅ |
| SS taxation | ✓ | ✓ | ✅ |
| Standard vs itemized optimization | ✓ | ❌ (std only) | ❌ |
| Lifetime tax total | ✓ | ✓ | ✅ |
| IRMAA (Part B/D) | ✓ | ✓ | ✅ |
| Tax-bracket-fill visualization | ✓ | ❌ | ❌ |

## 9. Social Security Explorer
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Claiming-age comparison / break-even | ✓ | ✓ | ✅ |
| Spousal / survivor modeling | ✓ | 🟡 (per-person; survivor in Wave 5) | 🟡 |

## 10. Medicare / Healthcare
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Medicare cost estimate (Part B/D, health tiers) | ✓ | ❌ | ❌ |
| IRMAA surcharges | ✓ | ✓ | ✅ |
| Pre-65 ACA as expense | ✓ | 🟡 (manual stream) | 🟡 |

## 11. Monte Carlo / Chance of Success
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Monte Carlo simulation | ✓ | ✓ (500 trials, per-year returns) | ✅ |
| Chance-of-success % (never-negative) | ✓ | ✓ | ✅ |
| Optimistic/Average/Pessimistic assumption sets | ✓ | ✓ (deterministic variants) | ✅ |

## 12. Projections / Metrics
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Net worth over time | ✓ | ✓ | ✅ |
| Cash flow | ✓ | ✓ | ✅ |
| Out-of-money / out-of-savings age | ✓ | ✓ | ✅ |
| Estate value at longevity | ✓ | ✓ | ✅ |
| Sankey cash-flow chart | ✓ | ❌ | ⛔? (nice-to-have) |

## 13. Insights / Coach
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Financial Wellness Score | ✓ | ❌ | ❌ |
| Coach alerts / suggestions | ✓ | 🟡 (validation warnings) | 🟡 |
| AI chat assistant | ✓ | ⛔ | ⛔ (non-goal) |

## 14. Scenarios / What-if
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Clone + compare scenarios | ✓ | ✓ | ✅ |
| Compare optimistic/avg/pess side by side | ✓ | 🟡 (run each variant) | 🟡 |

## 15. Inflation Assumptions
| Feature | Boldin | This app | Status |
|---|---|---|---|
| General + medical + SS COLA + housing | ✓ | 🟡 (no housing rate field) | 🟡 |

## 16. Reports / Charts / Export
| Feature | Boldin | This app | Status |
|---|---|---|---|
| CSV export | ✓ | ✓ | ✅ |
| 25+ charts | ✓ | 🟡 (6) | 🟡 |
| Printable PDF report | ✓ | ❌ | ❌ |

## 17. Annuity tools
| Feature | Boldin | This app | Status |
|---|---|---|---|
| Lifetime annuity calculator | ✓ | ❌ | ❌ |

---

## Out of scope (single-user / local-first / external service)
- Account aggregation / bank linking (explicit non-goal; external service)
- AI chat assistant, human CFP coaching, community/classes
- Mobile app, hosted multi-user, tiered paywall
- Real-time market sync

---

## Wave plan
- **Wave 1** — Accumulation economics: contributions + employer match; debt/mortgage
  amortization; home-sale events; lifetime-tax, out-of-money age, estate metrics. _(in progress)_
- **Wave 2** — Assumption sets (optimistic/avg/pessimistic) + Monte Carlo + chance of success.
- **Wave 3** — IRMAA + Medicare cost estimator + itemized deductions + ACA; tax charts.
- **Wave 4** — Social Security Explorer; Roth Conversion Explorer (bracket/IRMAA/lifetime).
- **Wave 5** — Insights/Wellness score; Money Flows; account exclusion; spending phases;
  extra account types; survivor modeling; more charts; PDF report.

## Audit log
- Round 0 (baseline): 279 tests passing. Gaps enumerated above.
- Wave 1a: Contributions + employer match (engine + API + UI + migration + tests).
  Pre-tax (401k/403b/457b/trad-IRA/HSA) reduce federal wages; employer-plan deferrals also reduce
  MA wages; Roth adds to contributions basis. Capped at available income so it never forces a
  withdrawal. Fixed latent bugs: CI was red (pre-existing mypy + ruff failures) — now green.
  Fixed crash: uniform lifetime RMD table only reached age 80; extended to official age 120 so
  realistic life expectancies (default 95) no longer crash. 286 tests passing.
</content>
