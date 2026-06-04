"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiRequest, type InsightsResult } from "../../../lib/api";

const ALERT_STYLES: Record<string, string> = {
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
  info: "border-sky-300 bg-sky-50 text-sky-900",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
  critical: "border-red-300 bg-red-50 text-red-900"
};

function scoreColor(score: number): string {
  if (score >= 85) return "text-emerald-700";
  if (score >= 70) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

export default function InsightsPage() {
  const params = useParams<{ id: string }>();
  const [insights, setInsights] = useState<InsightsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<InsightsResult>(`/scenarios/${params.id}/insights`)
      .then(setInsights)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Unable to load insights")
      );
  }, [params.id]);

  if (error) {
    return <main className="p-8 text-red-900">{error}</main>;
  }
  if (!insights) {
    return <main className="p-8 text-stone-600">Analyzing your plan…</main>;
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
          ← Back to scenario
        </Link>
        <h1 className="text-2xl font-semibold text-stone-950">Financial Wellness</h1>

        <section className="flex flex-col items-center gap-2 rounded-md border border-stone-300 bg-white p-8">
          <p className={`text-6xl font-bold ${scoreColor(insights.score)}`}>{insights.score}</p>
          <p className="text-lg font-semibold text-stone-700">{insights.rating}</p>
          <p className="text-sm text-stone-500">Financial wellness score (0–100)</p>
        </section>

        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="mb-4 text-base font-semibold text-stone-950">Score breakdown</h2>
          <div className="flex flex-col gap-4">
            {insights.components.map((c) => (
              <div key={c.label}>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-stone-800">
                    {c.label} <span className="text-stone-400">({c.weight}%)</span>
                  </span>
                  <span className="font-semibold text-stone-900">{c.score}</span>
                </div>
                <div className="mt-1 h-2 w-full rounded-full bg-stone-100">
                  <div
                    className="h-2 rounded-full bg-emerald-600"
                    style={{ width: `${Math.max(0, Math.min(100, c.score))}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-stone-500">{c.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-base font-semibold text-stone-950">
            Coach insights ({insights.alerts.length})
          </h2>
          {insights.alerts.length === 0 ? (
            <p className="text-sm text-stone-500">No alerts — your plan looks solid.</p>
          ) : (
            insights.alerts.map((a, i) => (
              <div
                className={`rounded-md border p-4 ${ALERT_STYLES[a.severity] ?? ALERT_STYLES.info}`}
                key={i}
              >
                <p className="text-sm font-semibold">{a.title}</p>
                <p className="mt-1 text-sm">{a.message}</p>
              </div>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
