"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  apiRequest,
  formatMoney,
  type ProjectionRun,
  type ScenarioDetail
} from "../../lib/api";

type ScenarioData = {
  scenario: ScenarioDetail;
  projection: ProjectionRun | null;
  error?: string;
};

function CompareContent() {
  const searchParams = useSearchParams();
  const idsParam = searchParams.get("ids") ?? "";
  const ids = idsParam
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const [scenarios, setScenarios] = useState<ScenarioData[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (ids.length === 0) {
      setIsLoading(false);
      return;
    }
    Promise.all(
      ids.map(async (id) => {
        try {
          const [scenario, projection] = await Promise.all([
            apiRequest<ScenarioDetail>(`/scenarios/${id}`),
            apiRequest<ProjectionRun>(`/scenarios/${id}/projection`).catch(() => null)
          ]);
          return { scenario, projection };
        } catch (err) {
          return {
            scenario: null as unknown as ScenarioDetail,
            projection: null,
            error: err instanceof Error ? err.message : "Unable to load"
          };
        }
      })
    )
      .then(setScenarios)
      .finally(() => setIsLoading(false));
  }, [idsParam]);

  if (isLoading) {
    return <p className="text-stone-600">Loading scenarios…</p>;
  }

  if (ids.length === 0) {
    return (
      <p className="text-stone-600">
        No scenario IDs provided. Use{" "}
        <code className="font-mono text-sm">/scenario/compare?ids=a,b,c</code>.
      </p>
    );
  }

  const loadedScenarios = scenarios.filter((s) => s.scenario && s.projection);
  if (loadedScenarios.length === 0) {
    return (
      <p className="text-stone-600">
        No scenarios with projections found. Run a projection for each scenario first.
      </p>
    );
  }

  // Build a sorted list of all years across scenarios
  const allYears = [
    ...new Set(
      loadedScenarios.flatMap((s) => s.projection!.years.map((y) => y.year))
    )
  ].sort((a, b) => a - b);

  const METRICS = [
    { key: "gross_income", label: "Income" },
    { key: "expenses", label: "Expenses" },
    { key: "federal_tax", label: "Federal tax" },
    { key: "magi", label: "MAGI" },
    { key: "surplus", label: "Surplus" },
    { key: "ending_net_worth", label: "Net worth" }
  ] as const;

  return (
    <>
      {/* Header row */}
      <div className="grid gap-3" style={{ gridTemplateColumns: `160px repeat(${loadedScenarios.length}, 1fr)` }}>
        <div />
        {loadedScenarios.map((s) => (
          <div className="rounded-md border border-stone-300 bg-white p-4" key={s.scenario.id}>
            <Link
              className="text-sm font-semibold text-emerald-700 hover:underline"
              href={`/scenario/${s.scenario.id}`}
            >
              {s.scenario.name}
            </Link>
            <p className="mt-1 text-xs text-stone-500">{s.scenario.household.name}</p>
          </div>
        ))}
      </div>

      {/* Metric rows */}
      {METRICS.map((metric) => (
        <div key={metric.key}>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
            {metric.label}
          </p>
          <div className="overflow-x-auto rounded-md border border-stone-300 bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-stone-200 bg-stone-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-stone-500">
                    Year
                  </th>
                  {loadedScenarios.map((s) => (
                    <th
                      className="px-4 py-2 text-right text-xs font-semibold text-stone-500"
                      key={s.scenario.id}
                    >
                      {s.scenario.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {allYears.map((year) => (
                  <tr className="hover:bg-stone-50" key={year}>
                    <td className="px-4 py-2 font-medium text-stone-700">{year}</td>
                    {loadedScenarios.map((s) => {
                      const row = s.projection!.years.find((y) => y.year === year);
                      const val = row ? row[metric.key] : null;
                      return (
                        <td
                          className={`px-4 py-2 text-right ${metric.key === "surplus" && val !== null && Number(val) < 0 ? "text-red-700" : ""}`}
                          key={s.scenario.id}
                        >
                          {val !== null ? formatMoney(val) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </>
  );
}

export default function ComparePage() {
  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <Link className="text-sm font-semibold text-emerald-800" href="/">
            ← All scenarios
          </Link>
        </div>
        <h1 className="text-2xl font-semibold text-stone-950">Scenario comparison</h1>
        <Suspense fallback={<p className="text-stone-600">Loading…</p>}>
          <CompareContent />
        </Suspense>
      </div>
    </main>
  );
}
