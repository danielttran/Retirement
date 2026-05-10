"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, deleteScenario, formatMoney, type Scenario, type ScenarioDetail } from "./lib/api";

type ScenarioRow = Scenario & {
  detail?: ScenarioDetail;
  detailError?: string;
};

export default function DashboardPage() {
  const [scenarios, setScenarios] = useState<ScenarioRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadScenarios() {
      try {
        const rows = await apiRequest<Scenario[]>("/scenarios");
        const withDetails = await Promise.all(
          rows.map(async (scenario) => {
            try {
              return {
                ...scenario,
                detail: await apiRequest<ScenarioDetail>(`/scenarios/${scenario.id}`)
              };
            } catch (err) {
              return {
                ...scenario,
                detailError:
                  err instanceof Error ? err.message : "Unable to load scenario details"
              };
            }
          })
        );
        if (isMounted) {
          setScenarios(withDetails);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Unable to load scenarios");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadScenarios();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-5 border-b border-stone-300 pb-6 md:flex-row md:items-end md:justify-between">
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium uppercase tracking-wide text-emerald-700">
              Local planner
            </p>
            <h1 className="text-4xl font-semibold text-stone-950">Personal Retirement Planner</h1>
            <p className="max-w-3xl text-base leading-7 text-stone-700">
              Create a household, save scenarios, add accounts, and build toward deterministic
              retirement projections.
            </p>
          </div>
          <Link
            className="inline-flex h-11 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800"
            href="/household/new"
          >
            New household
          </Link>
        </header>

        {error ? (
          <section className="rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-900">
            API unavailable: {error}
          </section>
        ) : null}

        <section className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
          This tool is for educational planning only. It is not tax, legal, investment, or financial
          advice. Confirm any retirement-account distribution or conversion plan with a qualified
          tax professional before acting.
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-stone-950">Scenarios</h2>
            <span className="text-sm text-stone-600">{scenarios.length} saved</span>
          </div>

          {isLoading ? (
            <div className="rounded-md border border-stone-300 bg-white p-5 text-stone-600">
              Loading scenarios...
            </div>
          ) : scenarios.length === 0 ? (
            <div className="rounded-md border border-stone-300 bg-white p-5">
              <h3 className="text-base font-semibold text-stone-950">No scenarios yet</h3>
              <p className="mt-2 text-sm leading-6 text-stone-600">
                Start with a household profile. The app will create a baseline scenario that you can
                open and populate with accounts.
              </p>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {scenarios.map((scenario) => (
                <div
                  className="relative rounded-md border border-stone-300 bg-white shadow-sm transition hover:border-emerald-600"
                  key={scenario.id}
                >
                  <Link
                    className="block p-5"
                    href={`/scenario/${scenario.id}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="text-lg font-semibold text-stone-950">{scenario.name}</h3>
                        <p className="mt-1 text-sm text-stone-600">
                          {scenario.detail?.household.name ?? "Household"}
                        </p>
                      </div>
                      <span className="text-sm font-semibold text-emerald-800">
                        {formatMoney(scenario.detail?.total_account_balance ?? "0")}
                      </span>
                    </div>
                    <p className="mt-4 text-sm text-stone-600">
                      {scenario.detailError
                        ? "Details unavailable"
                        : `${scenario.detail?.accounts.length ?? 0} accounts saved`}
                    </p>
                  </Link>
                  <button
                    className="absolute right-3 top-3 rounded p-1 text-stone-400 hover:bg-red-50 hover:text-red-600"
                    onClick={(e) => {
                      e.preventDefault();
                      if (!confirm(`Delete scenario "${scenario.name}"? This cannot be undone.`)) return;
                      void deleteScenario(scenario.id).then(() => {
                        setScenarios((prev) => prev.filter((s) => s.id !== scenario.id));
                      });
                    }}
                    title="Delete scenario"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
