"use client";

import type { Route } from "next";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  apiRequest,
  downloadCsv,
  formatMoney,
  type ProjectionRun,
  type ProjectionWarning
} from "../../../lib/api";

const DISCLAIMER =
  "This tool is for educational planning only. It is not tax, legal, investment, or financial advice. 72(t)/SEPP rules are strict, and improper changes can trigger penalties, recapture tax, and interest. Roth conversion strategies have multi-year tax and ACA implications. Confirm any actual retirement-account distribution or conversion plan with a qualified tax professional before acting.";

function formatK(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export default function ProjectionPage() {
  const params = useParams<{ id: string }>();
  const [projection, setProjection] = useState<ProjectionRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warningsDismissed, setWarningsDismissed] = useState(false);
  const [showInfos, setShowInfos] = useState(false);

  useEffect(() => {
    apiRequest<ProjectionRun>(`/scenarios/${params.id}/projection`)
      .then(setProjection)
      .catch(() => {
        // No prior projection — that's fine
      });
  }, [params.id]);

  const errors = projection?.warnings.filter((w) => w.severity === "error") ?? [];
  const warnings = projection?.warnings.filter((w) => w.severity === "warning") ?? [];
  const infos = projection?.warnings.filter((w) => w.severity === "info") ?? [];

  async function runProjection() {
    setIsRunning(true);
    setError(null);
    setWarningsDismissed(false);
    try {
      const result = await apiRequest<ProjectionRun>(`/scenarios/${params.id}/run-projection`, {
        method: "POST"
      });
      setProjection(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Projection failed");
    } finally {
      setIsRunning(false);
    }
  }

  function exportYears() {
    if (!projection) return;
    downloadCsv(
      `projection_year_${params.id}_${projection.metadata.run_at.slice(0, 10)}.csv`,
      projection.years as unknown as Record<string, unknown>[]
    );
  }

  function exportBalances() {
    if (!projection) return;
    downloadCsv(
      `projection_account_balance_${params.id}_${projection.metadata.run_at.slice(0, 10)}.csv`,
      projection.account_balances as unknown as Record<string, unknown>[]
    );
  }

  const chartData =
    projection?.years.map((y) => ({
      year: y.year,
      netWorth: Number(y.ending_net_worth),
      income: Number(y.gross_income) + Number(y.required_distributions) + Number(y.flexible_withdrawals),
      expenses: Number(y.expenses) + Number(y.federal_tax) + Number(y.state_tax)
    })) ?? [];

  const hasErrors = errors.length > 0;

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex items-center justify-between">
          <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
            ← Back to scenario
          </Link>
          {projection ? (
            <Link
              className="text-sm font-semibold text-emerald-700 hover:underline"
              href={`/scenario/${params.id}/charts` as Route}
            >
              View all charts →
            </Link>
          ) : null}
        </div>

        {/* Disclaimer — §17 */}
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
          {DISCLAIMER}
        </div>

        {/* Error warnings block run button — §14.3 */}
        {hasErrors ? (
          <div className="rounded-md border border-red-400 bg-red-50 p-4">
            <p className="mb-2 text-sm font-semibold text-red-900">
              {errors.length} error{errors.length !== 1 ? "s" : ""} must be resolved before running:
            </p>
            <ul className="list-inside list-disc space-y-1 text-sm text-red-800">
              {errors.map((w: ProjectionWarning) => (
                <li key={w.id}>
                  <span className="font-mono text-xs">{w.code}</span>
                  {w.year ? ` (${w.year})` : ""}: {w.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* Run button */}
        <div className="flex items-center gap-4">
          <button
            className="inline-flex h-11 items-center justify-center rounded-md bg-emerald-700 px-6 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-60"
            disabled={isRunning || hasErrors}
            onClick={() => { void runProjection(); }}
            type="button"
          >
            {isRunning ? "Running…" : projection ? "Re-run Projection" : "Run Projection"}
          </button>
          {projection ? (
            <>
              <button
                className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                onClick={exportYears}
                type="button"
              >
                Export years CSV
              </button>
              <button
                className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                onClick={exportBalances}
                type="button"
              >
                Export balances CSV
              </button>
            </>
          ) : null}
        </div>

        {error ? (
          <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
            {error}
          </div>
        ) : null}

        {/* Warnings panel — §14.3 */}
        {!warningsDismissed && warnings.length > 0 ? (
          <div className="rounded-md border border-yellow-400 bg-yellow-50 p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-semibold text-yellow-900">
                {warnings.length} warning{warnings.length !== 1 ? "s" : ""}
              </p>
              <button
                className="text-sm text-yellow-700 hover:underline"
                onClick={() => setWarningsDismissed(true)}
                type="button"
              >
                Dismiss
              </button>
            </div>
            <ul className="list-inside list-disc space-y-1 text-sm text-yellow-800">
              {warnings.map((w: ProjectionWarning) => (
                <li key={w.id}>
                  <span className="font-mono text-xs">{w.code}</span>
                  {w.year ? ` (${w.year})` : ""}: {w.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* Info expander — §14.3 */}
        {infos.length > 0 ? (
          <div className="rounded-md border border-stone-300 bg-stone-50 p-3">
            <button
              className="flex w-full items-center justify-between text-sm font-semibold text-stone-700"
              onClick={() => setShowInfos(!showInfos)}
              type="button"
            >
              <span>{infos.length} info note{infos.length !== 1 ? "s" : ""}</span>
              <span>{showInfos ? "▲" : "▼"}</span>
            </button>
            {showInfos ? (
              <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-stone-600">
                {infos.map((w: ProjectionWarning) => (
                  <li key={w.id}>
                    <span className="font-mono text-xs">{w.code}</span>
                    {w.year ? ` (${w.year})` : ""}: {w.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {projection ? (
          <>
            <div className="text-xs text-stone-400">
              Run {projection.metadata.run_at.slice(0, 19).replace("T", " ")} · engine{" "}
              {projection.metadata.engine_version} · IRS {projection.metadata.irs_data_version}
            </div>

            {/* Net Worth chart */}
            <section className="rounded-md border border-stone-300 bg-white p-5">
              <h2 className="mb-4 text-base font-semibold text-stone-950">
                Net Worth Over Time
              </h2>
              <ResponsiveContainer height={280} width="100%">
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
                  <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={formatK} tick={{ fontSize: 12 }} width={72} />
                  <Tooltip formatter={(v: number) => formatMoney(v)} />
                  <Area
                    dataKey="netWorth"
                    fill="#d1fae5"
                    name="Net worth"
                    stroke="#059669"
                    type="monotone"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </section>

            {/* Year-by-year table */}
            <section className="rounded-md border border-stone-300 bg-white">
              <div className="border-b border-stone-200 px-5 py-4">
                <h2 className="text-base font-semibold text-stone-950">
                  Year-by-year summary ({projection.years.length} years)
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-stone-200 bg-stone-50">
                    <tr>
                      {[
                        "Year",
                        "Age",
                        "Income",
                        "Distributions",
                        "Expenses",
                        "Federal tax",
                        "State tax",
                        "MAGI",
                        "Surplus",
                        "Net worth"
                      ].map((h) => (
                        <th
                          className="px-4 py-3 text-right text-xs font-semibold text-stone-500 first:text-left"
                          key={h}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    {projection.years.map((row) => (
                      <tr className="hover:bg-stone-50" key={row.year}>
                        <td className="px-4 py-2 font-medium text-stone-950">{row.year}</td>
                        <td className="px-4 py-2 text-right text-stone-600">
                          {row.age_primary}
                          {row.age_spouse ? `/${row.age_spouse}` : ""}
                        </td>
                        <td className="px-4 py-2 text-right">{formatMoney(row.gross_income)}</td>
                        <td className="px-4 py-2 text-right">
                          {formatMoney(
                            Number(row.required_distributions) + Number(row.flexible_withdrawals)
                          )}
                        </td>
                        <td className="px-4 py-2 text-right">{formatMoney(row.expenses)}</td>
                        <td className="px-4 py-2 text-right">{formatMoney(row.federal_tax)}</td>
                        <td className="px-4 py-2 text-right">{formatMoney(row.state_tax)}</td>
                        <td className="px-4 py-2 text-right">{formatMoney(row.magi)}</td>
                        <td
                          className={`px-4 py-2 text-right font-medium ${Number(row.surplus) < 0 ? "text-red-700" : "text-emerald-700"}`}
                        >
                          {formatMoney(row.surplus)}
                        </td>
                        <td className="px-4 py-2 text-right font-semibold text-stone-950">
                          {formatMoney(row.ending_net_worth)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
