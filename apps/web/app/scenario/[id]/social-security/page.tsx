"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  apiRequest,
  formatMoney,
  type Person,
  type ScenarioDetail,
  type SocialSecurityExplorerResult
} from "../../../lib/api";

function fmtK(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export default function SocialSecurityPage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [personId, setPersonId] = useState<string | null>(null);
  const [result, setResult] = useState<SocialSecurityExplorerResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<ScenarioDetail>(`/scenarios/${params.id}`)
      .then((s) => {
        setScenario(s);
        const primary = s.household.people.find((p) => p.is_primary) ?? s.household.people[0];
        setPersonId(primary?.id ?? null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Unable to load scenario")
      );
  }, [params.id]);

  useEffect(() => {
    if (!personId) return;
    apiRequest<SocialSecurityExplorerResult>(
      `/scenarios/${params.id}/social-security-explorer?person_id=${personId}`
    )
      .then(setResult)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Unable to load explorer")
      );
  }, [params.id, personId]);

  if (error) {
    return <main className="p-8 text-red-900">{error}</main>;
  }
  if (!scenario || !result) {
    return <main className="p-8 text-stone-600">Loading Social Security explorer…</main>;
  }

  const fraYears = Math.floor(result.full_retirement_age_months / 12);
  const fraMonths = result.full_retirement_age_months % 12;
  const chartData = result.options.map((o) => ({
    age: o.claiming_age,
    annual: Number(o.annual_benefit),
    lifetime: Number(o.lifetime_total)
  }));

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
          ← Back to scenario
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-stone-950">Social Security Explorer</h1>
            <p className="mt-1 text-sm text-stone-500">
              Full Retirement Age {fraYears}
              {fraMonths ? ` yr ${fraMonths} mo` : ""} · estimated PIA{" "}
              {formatMoney(result.pia_annual)}/yr
              {result.current_claiming_age
                ? ` · current plan claims at ${result.current_claiming_age}`
                : " · no Social Security income entered yet"}
            </p>
          </div>
          {scenario.household.people.length > 1 ? (
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Person
              <select
                className="h-10 rounded-md border border-stone-300 px-2"
                onChange={(e) => setPersonId(e.target.value)}
                value={personId ?? ""}
              >
                {scenario.household.people.map((p: Person) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        <div className="rounded-md border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900">
          Claiming at <strong>age {result.max_lifetime_claiming_age}</strong> maximizes total
          lifetime benefits given this longevity assumption.
        </div>

        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">
            Lifetime benefit by claiming age
          </h2>
          <ResponsiveContainer height={300} width="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="age" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={68} />
              <Tooltip formatter={(v: number) => formatMoney(v)} />
              <Legend />
              <Bar dataKey="lifetime" fill="#059669" name="Lifetime total" />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-base font-semibold text-stone-950">Claiming-age comparison</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-stone-200 bg-stone-50 text-xs text-stone-500">
                <tr>
                  <th className="px-4 py-3 text-left">Claiming age</th>
                  <th className="px-4 py-3 text-right">Monthly</th>
                  <th className="px-4 py-3 text-right">Annual</th>
                  <th className="px-4 py-3 text-right">Lifetime total</th>
                  <th className="px-4 py-3 text-right">Break-even vs age 62</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {result.options.map((o) => (
                  <tr
                    className={
                      o.claiming_age === result.max_lifetime_claiming_age
                        ? "bg-emerald-50"
                        : "hover:bg-stone-50"
                    }
                    key={o.claiming_age}
                  >
                    <td className="px-4 py-2 font-medium text-stone-950">
                      {o.claiming_age}
                      {o.claiming_age === result.current_claiming_age ? " (current)" : ""}
                    </td>
                    <td className="px-4 py-2 text-right">{formatMoney(o.monthly_benefit)}</td>
                    <td className="px-4 py-2 text-right">{formatMoney(o.annual_benefit)}</td>
                    <td className="px-4 py-2 text-right font-semibold">
                      {formatMoney(o.lifetime_total)}
                    </td>
                    <td className="px-4 py-2 text-right text-stone-500">
                      {o.break_even_age_vs_earliest ? `age ${o.break_even_age_vs_earliest}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
