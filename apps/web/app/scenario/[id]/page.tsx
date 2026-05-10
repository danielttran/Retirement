"use client";

import type { Route } from "next";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiRequest, deleteHousehold, deleteScenario, formatMoney, type ScenarioDetail } from "../../lib/api";

const NAV_ITEMS = [
  { href: "accounts", label: "Accounts", description: "Cash, brokerage, IRA, 401(k), Roth, HSA" },
  { href: "income", label: "Income", description: "Salary, pension, Social Security, annuity" },
  { href: "expenses", label: "Expenses", description: "Must-spend, discretionary, healthcare" },
  { href: "sepp", label: "SEPP / 72(t)", description: "Substantially equal periodic payment plans" },
  {
    href: "roth-conversions",
    label: "Roth Conversions",
    description: "Year-by-year conversion schedule"
  },
  { href: "withdrawal", label: "Withdrawal Strategy", description: "Account drawdown order" },
  { href: "assumptions", label: "Assumptions", description: "Inflation rates, IRS data version" },
  {
    href: "projection",
    label: "Projection",
    description: "Run and view year-by-year results",
    highlight: true
  },
  { href: "charts", label: "Charts", description: "Net worth, cash flow, taxes, MAGI" }
];

export default function ScenarioPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadScenario() {
      try {
        setScenario(await apiRequest<ScenarioDetail>(`/scenarios/${params.id}`));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load scenario");
      }
    }

    void loadScenario();
  }, [params.id]);

  if (error) {
    return <main className="p-8 text-red-900">{error}</main>;
  }

  if (!scenario) {
    return <main className="p-8 text-stone-600">Loading scenario...</main>;
  }

  const primaryPerson = scenario.household.people.find((p) => p.is_primary);

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-7">
        <header className="flex flex-col gap-4 border-b border-stone-300 pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <Link className="text-sm font-semibold text-emerald-700" href="/">
              ← All scenarios
            </Link>
            <p className="mt-3 text-sm font-medium uppercase tracking-wide text-emerald-700">
              {scenario.household.name}
            </p>
            <h1 className="mt-1 text-3xl font-semibold text-stone-950">{scenario.name}</h1>
            <p className="mt-2 text-sm text-stone-600">
              Filing: {scenario.household.filing_status.toUpperCase()} · State:{" "}
              {scenario.household.state}
              {primaryPerson ? ` · ${primaryPerson.name}` : ""}
            </p>
          </div>
          <Link
            className="inline-flex h-11 items-center justify-center rounded-md bg-emerald-700 px-5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800"
            href={`/scenario/${scenario.id}/projection` as Route}
          >
            Run Projection
          </Link>
        </header>

        <section className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-stone-300 bg-white p-5">
            <p className="text-sm text-stone-500">Total balance</p>
            <p className="mt-2 text-2xl font-semibold text-stone-950">
              {formatMoney(scenario.total_account_balance)}
            </p>
          </div>
          <div className="rounded-md border border-stone-300 bg-white p-5">
            <p className="text-sm text-stone-500">Accounts</p>
            <p className="mt-2 text-2xl font-semibold text-stone-950">
              {scenario.accounts.length}
            </p>
          </div>
          <div className="rounded-md border border-stone-300 bg-white p-5">
            <p className="text-sm text-stone-500">Primary person</p>
            <p className="mt-2 text-xl font-semibold text-stone-950">
              {primaryPerson?.name ?? "—"}
            </p>
            {primaryPerson?.dob ? (
              <p className="mt-1 text-sm text-stone-500">Born {primaryPerson.dob}</p>
            ) : null}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold text-stone-950">Plan inputs</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {NAV_ITEMS.map((item) => (
              <Link
                className={`flex flex-col gap-1 rounded-md border p-5 transition hover:border-emerald-600 ${
                  item.highlight
                    ? "border-emerald-400 bg-emerald-50"
                    : "border-stone-300 bg-white"
                }`}
                href={`/scenario/${scenario.id}/${item.href}` as Route}
                key={item.href}
              >
                <span
                  className={`text-base font-semibold ${item.highlight ? "text-emerald-900" : "text-stone-950"}`}
                >
                  {item.label}
                </span>
                <span className="text-sm text-stone-500">{item.description}</span>
              </Link>
            ))}
          </div>
        </section>

        <section>
          <Link
            className="text-sm font-semibold text-emerald-700 hover:underline"
            href={`/scenario/compare?ids=${scenario.id}` as Route}
          >
            Compare scenarios →
          </Link>
        </section>

        <section className="rounded-md border border-red-200 bg-red-50 p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-red-700">
            Danger zone
          </h2>
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              className="inline-flex h-10 items-center justify-center rounded-md border border-red-300 bg-white px-4 text-sm font-semibold text-red-700 hover:bg-red-100"
              onClick={() => {
                if (!confirm(`Delete scenario "${scenario.name}"? This cannot be undone.`)) return;
                void deleteScenario(scenario.id).then(() => router.push("/"));
              }}
            >
              Delete scenario
            </button>
            <button
              className="inline-flex h-10 items-center justify-center rounded-md border border-red-300 bg-white px-4 text-sm font-semibold text-red-700 hover:bg-red-100"
              onClick={() => {
                if (
                  !confirm(
                    `Delete household "${scenario.household.name}" and ALL its scenarios? This cannot be undone.`
                  )
                )
                  return;
                void deleteHousehold(scenario.household_id).then(() => router.push("/"));
              }}
            >
              Delete household &amp; all scenarios
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
