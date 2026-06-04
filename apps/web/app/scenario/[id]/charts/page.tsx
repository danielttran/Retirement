"use client";

import type { Route } from "next";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Sankey,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  apiRequest,
  formatMoney,
  type Account,
  type ProjectionAccountBalance,
  type ProjectionRun,
  type ScenarioDetail,
  type SeppPlan
} from "../../../lib/api";

function fmtK(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

// ACA FPL thresholds for single person 2024 (approximate); displayed as reference lines
// Actual values would come from irs_data but hardcoding for display purposes
const ACA_FPL_SINGLE_2024 = 14580;
const ACA_MULTIPLES = [1.0, 1.38, 1.5, 2.0, 2.5, 4.0];

const AREA_COLORS = [
  "#059669", "#0284c7", "#7c3aed", "#d97706", "#dc2626", "#0891b2", "#65a30d"
];

type AccountTypeSeries = Record<string, number>;

export default function ChartsPage() {
  const params = useParams<{ id: string }>();
  const [projection, setProjection] = useState<ProjectionRun | null>(null);
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [seppPlans, setSeppPlans] = useState<SeppPlan[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiRequest<ProjectionRun>(`/scenarios/${params.id}/projection`),
      apiRequest<ScenarioDetail>(`/scenarios/${params.id}`),
      apiRequest<SeppPlan[]>(`/scenarios/${params.id}/sepp-plans`)
    ])
      .then(([proj, sc, sepp]) => {
        setProjection(proj);
        setScenario(sc);
        setSeppPlans(sepp);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load projection");
      });
  }, [params.id]);

  if (error) {
    return (
      <main className="p-8">
        <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}/projection` as Route}>
          ← Back to projection
        </Link>
        <p className="mt-4 text-red-900">{error} — run a projection first.</p>
      </main>
    );
  }

  if (!projection || !scenario) {
    return <main className="p-8 text-stone-600">Loading charts…</main>;
  }

  const accounts = scenario.accounts;

  // --- Chart 1: Net worth over time (stacked area by account type) ---
  const accountTypeSet = [...new Set(accounts.map((a: Account) => a.account_type))];
  const netWorthData = projection.years.map((y) => {
    const byType: AccountTypeSeries = {};
    const yearBalances = projection.account_balances.filter(
      (b: ProjectionAccountBalance) => b.year === y.year
    );
    for (const acct of accounts) {
      const bal = yearBalances.find((b: ProjectionAccountBalance) => b.account_id === acct.id);
      const ending = Number(bal?.ending_balance ?? 0);
      byType[acct.account_type] = (byType[acct.account_type] ?? 0) + ending;
    }
    return { year: y.year, ...byType };
  });

  // --- Chart 2: Per-account balances ---
  const perAccountData = projection.years.map((y) => {
    const row: Record<string, number> = { year: y.year };
    const yearBalances = projection.account_balances.filter(
      (b: ProjectionAccountBalance) => b.year === y.year
    );
    for (const acct of accounts) {
      const bal = yearBalances.find((b: ProjectionAccountBalance) => b.account_id === acct.id);
      row[acct.name] = Number(bal?.ending_balance ?? 0);
    }
    return row;
  });

  // --- Chart 3: Cash flow ---
  const cashFlowData = projection.years.map((y) => ({
    year: y.year,
    income: Number(y.gross_income),
    distributions:
      Number(y.required_distributions) + Number(y.flexible_withdrawals),
    expenses: Number(y.expenses),
    taxes: Number(y.federal_tax) + Number(y.state_tax) + Number(y.early_withdrawal_penalty),
    surplus: Number(y.surplus)
  }));

  // --- Chart 4: Tax breakdown ---
  const taxData = projection.years.map((y) => ({
    year: y.year,
    federal: Number(y.federal_tax),
    state: Number(y.state_tax),
    penalty: Number(y.early_withdrawal_penalty)
  }));

  // --- Chart 5: SEPP payments ---
  const activeSeppPlans = seppPlans.filter(
    (p) => p.status === "active" || p.status === "planned"
  );
  const seppData = projection.years.map((y) => {
    const row: Record<string, number> = { year: y.year };
    for (const plan of activeSeppPlans) {
      const acct = accounts.find((a: Account) => a.id === plan.account_id);
      const label = acct?.name ?? plan.id.slice(0, 8);
      const payment = plan.initial_annual_payment_locked
        ? Number(plan.initial_annual_payment_locked)
        : 0;
      const firstYear = new Date(plan.first_payment_date).getFullYear();
      const lastYear = new Date(plan.required_end_date).getFullYear();
      row[label] = y.year >= firstYear && y.year <= lastYear ? payment : 0;
    }
    return row;
  });

  // --- Chart 6: MAGI vs ACA thresholds ---
  const magiData = projection.years
    .filter((y) => y.age_primary < 65)
    .map((y) => ({ year: y.year, magi: Number(y.magi) }));

  // --- Chart 7: Roth conversions + IRMAA surcharges ---
  const conversionIrmaaData = projection.years.map((y) => ({
    year: y.year,
    conversions: Number(y.roth_conversions),
    irmaa: Number(y.medicare_irmaa)
  }));
  const hasConversionsOrIrmaa = conversionIrmaaData.some(
    (r) => r.conversions > 0 || r.irmaa > 0
  );

  // --- Chart 8: Tax-bracket fill (ordinary taxable income vs 2024 bracket tops) ---
  const BRACKET_TOPS_2024: Record<string, { rate: string; top: number }[]> = {
    single: [
      { rate: "10%", top: 11600 },
      { rate: "12%", top: 47150 },
      { rate: "22%", top: 100525 },
      { rate: "24%", top: 191950 },
      { rate: "32%", top: 243725 },
      { rate: "35%", top: 609350 }
    ],
    mfj: [
      { rate: "10%", top: 23200 },
      { rate: "12%", top: 94300 },
      { rate: "22%", top: 201050 },
      { rate: "24%", top: 383900 },
      { rate: "32%", top: 487450 },
      { rate: "35%", top: 731200 }
    ]
  };
  const filingStatus = scenario.household.filing_status === "mfj" ? "mfj" : "single";
  const bracketTops = BRACKET_TOPS_2024[filingStatus];
  const bracketData = projection.years.map((y) => ({
    year: y.year,
    taxable: Number(y.ordinary_taxable_income)
  }));

  // --- Chart 9: Sankey lifetime cash flow ---
  const projectionYears = projection.years;
  const sumBy = (fn: (y: (typeof projectionYears)[number]) => number) =>
    projectionYears.reduce((acc, y) => acc + fn(y), 0);
  const sankeyIncome = sumBy((y) => Number(y.gross_income));
  const sankeyWithdrawals = sumBy(
    (y) => Number(y.required_distributions) + Number(y.flexible_withdrawals)
  );
  const sankeyTaxes = sumBy(
    (y) =>
      Number(y.federal_tax) +
      Number(y.state_tax) +
      Number(y.early_withdrawal_penalty) +
      Number(y.medicare_irmaa)
  );
  const sankeyExpenses = sumBy((y) => Number(y.expenses));
  const sankeyTotalCash = sankeyIncome + sankeyWithdrawals;
  const sankeySurplus = Math.max(0, sankeyTotalCash - sankeyTaxes - sankeyExpenses);
  const sankeyData = {
    nodes: [
      { name: "Income & SS" },
      { name: "Withdrawals" },
      { name: "Total cash" },
      { name: "Taxes" },
      { name: "Living expenses" },
      { name: "Surplus / savings" }
    ],
    links: [
      { source: 0, target: 2, value: Math.max(1, sankeyIncome) },
      { source: 1, target: 2, value: Math.max(1, sankeyWithdrawals) },
      { source: 2, target: 3, value: Math.max(1, sankeyTaxes) },
      { source: 2, target: 4, value: Math.max(1, sankeyExpenses) },
      { source: 2, target: 5, value: Math.max(1, sankeySurplus) }
    ]
  };

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <div className="flex items-center justify-between">
          <Link
            className="text-sm font-semibold text-emerald-800"
            href={`/scenario/${params.id}/projection` as Route}
          >
            ← Back to projection
          </Link>
          <p className="text-sm text-stone-500">
            Run {projection.metadata.run_at.slice(0, 10)}
          </p>
        </div>

        <h1 className="text-2xl font-semibold text-stone-950">Charts</h1>

        {/* Chart 1: Net Worth Over Time */}
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">
            1. Net Worth Over Time (by account type)
          </h2>
          <ResponsiveContainer height={300} width="100%">
            <AreaChart data={netWorthData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="year" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
              <Tooltip formatter={(v: number) => formatMoney(v)} />
              <Legend />
              {accountTypeSet.map((type, i) => (
                <Area
                  dataKey={type}
                  fill={AREA_COLORS[i % AREA_COLORS.length]}
                  fillOpacity={0.6}
                  key={type}
                  name={type}
                  stackId="1"
                  stroke={AREA_COLORS[i % AREA_COLORS.length]}
                  type="monotone"
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </section>

        {/* Chart 2: Per-Account Balances */}
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">
            2. Per-Account Balances
          </h2>
          <ResponsiveContainer height={300} width="100%">
            <LineChart data={perAccountData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="year" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
              <Tooltip formatter={(v: number) => formatMoney(v)} />
              <Legend />
              {accounts.map((acct: Account, i: number) => (
                <Line
                  dataKey={acct.name}
                  dot={false}
                  key={acct.id}
                  name={acct.name}
                  stroke={AREA_COLORS[i % AREA_COLORS.length]}
                  type="monotone"
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </section>

        {/* Chart 3: Cash Flow */}
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">3. Cash Flow</h2>
          <ResponsiveContainer height={300} width="100%">
            <BarChart data={cashFlowData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="year" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
              <Tooltip formatter={(v: number) => formatMoney(v)} />
              <Legend />
              <Bar dataKey="income" fill="#059669" name="Income" stackId="in" />
              <Bar dataKey="distributions" fill="#34d399" name="Distributions" stackId="in" />
              <Bar dataKey="expenses" fill="#f87171" name="Expenses" stackId="out" />
              <Bar dataKey="taxes" fill="#fca5a5" name="Taxes" stackId="out" />
            </BarChart>
          </ResponsiveContainer>
        </section>

        {/* Chart 4: Tax Breakdown */}
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">4. Tax Breakdown</h2>
          <ResponsiveContainer height={280} width="100%">
            <BarChart data={taxData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="year" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
              <Tooltip formatter={(v: number) => formatMoney(v)} />
              <Legend />
              <Bar dataKey="federal" fill="#1d4ed8" name="Federal" stackId="1" />
              <Bar dataKey="state" fill="#7c3aed" name="State" stackId="1" />
              <Bar dataKey="penalty" fill="#dc2626" name="Early-withdrawal penalty" stackId="1" />
            </BarChart>
          </ResponsiveContainer>
        </section>

        {/* Chart 5: SEPP Payments */}
        {activeSeppPlans.length > 0 ? (
          <section className="rounded-md border border-stone-300 bg-white p-5">
            <h2 className="mb-4 text-base font-semibold text-stone-950">5. SEPP Payments</h2>
            <ResponsiveContainer height={260} width="100%">
              <LineChart data={seppData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
                <Tooltip formatter={(v: number) => formatMoney(v)} />
                <Legend />
                {activeSeppPlans.map((plan, i) => {
                  const acct = accounts.find((a: Account) => a.id === plan.account_id);
                  const label = acct?.name ?? plan.id.slice(0, 8);
                  return (
                    <Line
                      dataKey={label}
                      dot={false}
                      key={plan.id}
                      name={label}
                      stroke={AREA_COLORS[i % AREA_COLORS.length]}
                      type="stepAfter"
                    />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          </section>
        ) : (
          <section className="rounded-md border border-stone-200 bg-stone-50 p-5 text-sm text-stone-500">
            5. SEPP Payments — no active SEPP plans.
          </section>
        )}

        {/* Chart 6: MAGI vs ACA Thresholds */}
        {magiData.length > 0 ? (
          <section className="rounded-md border border-stone-300 bg-white p-5">
            <h2 className="mb-4 text-base font-semibold text-stone-950">
              6. MAGI vs. ACA Thresholds (pre-65 years)
            </h2>
            <p className="mb-3 text-xs text-stone-400">
              FPL thresholds based on 2024 single-person FPL ($14,580). Scaled from irs_data ACA
              table in a full implementation; shown as approximate reference lines here.
            </p>
            <ResponsiveContainer height={280} width="100%">
              <LineChart data={magiData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
                <Tooltip formatter={(v: number) => formatMoney(v)} />
                <Legend />
                <Line
                  dataKey="magi"
                  dot={false}
                  name="MAGI"
                  stroke="#059669"
                  strokeWidth={2}
                  type="monotone"
                />
                {ACA_MULTIPLES.map((mult) => (
                  <ReferenceLine
                    key={mult}
                    label={{
                      value: `${mult * 100}% FPL`,
                      position: "right",
                      fontSize: 10
                    }}
                    stroke="#94a3b8"
                    strokeDasharray="4 2"
                    y={ACA_FPL_SINGLE_2024 * mult}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </section>
        ) : (
          <section className="rounded-md border border-stone-200 bg-stone-50 p-5 text-sm text-stone-500">
            6. MAGI vs. ACA Thresholds — no pre-65 years in projection.
          </section>
        )}

        {/* Chart 7: Roth conversions + IRMAA */}
        {hasConversionsOrIrmaa ? (
          <section className="rounded-md border border-stone-300 bg-white p-5">
            <h2 className="mb-4 text-base font-semibold text-stone-950">
              7. Roth Conversions &amp; Medicare IRMAA
            </h2>
            <ResponsiveContainer height={280} width="100%">
              <BarChart data={conversionIrmaaData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
                <Tooltip formatter={(v: number) => formatMoney(v)} />
                <Legend />
                <Bar dataKey="conversions" fill="#7c3aed" name="Roth conversions" />
                <Bar dataKey="irmaa" fill="#dc2626" name="IRMAA surcharge" />
              </BarChart>
            </ResponsiveContainer>
          </section>
        ) : null}

        {/* Chart 8: Tax-bracket fill */}
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">
            8. Tax-Bracket Fill (ordinary taxable income vs {filingStatus.toUpperCase()} brackets)
          </h2>
          <p className="mb-3 text-xs text-stone-400">
            Gaps below a bracket line reveal headroom for Roth conversions. Bracket tops shown in
            2024 dollars.
          </p>
          <ResponsiveContainer height={300} width="100%">
            <LineChart data={bracketData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="year" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
              <Tooltip formatter={(v: number) => formatMoney(v)} />
              <Line
                dataKey="taxable"
                dot={false}
                name="Ordinary taxable income"
                stroke="#059669"
                strokeWidth={2}
                type="monotone"
              />
              {bracketTops.map((b) => (
                <ReferenceLine
                  key={b.rate}
                  label={{ value: b.rate, position: "right", fontSize: 10 }}
                  stroke="#94a3b8"
                  strokeDasharray="4 2"
                  y={b.top}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </section>

        {/* Chart 9: Sankey lifetime cash flow */}
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">
            9. Lifetime Cash Flow (Sankey)
          </h2>
          <ResponsiveContainer height={320} width="100%">
            <Sankey
              data={sankeyData}
              link={{ stroke: "#a7f3d0" }}
              node={{ fill: "#059669" }}
              nodePadding={30}
            >
              <Tooltip formatter={(v: number) => formatMoney(v)} />
            </Sankey>
          </ResponsiveContainer>
        </section>
      </div>
    </main>
  );
}
