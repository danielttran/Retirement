"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  apiRequest,
  formatMoney,
  type Account,
  type RothConversionPlan,
  type RothExplorerResult,
  type ScenarioDetail
} from "../../../lib/api";

const TRADITIONAL_TYPES = [
  "traditional_ira",
  "traditional_401k",
  "traditional_403b",
  "governmental_457b"
];
const ROTH_TYPES = ["roth_ira", "roth_401k"];

export default function RothConversionsPage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [conversions, setConversions] = useState<RothConversionPlan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [explorer, setExplorer] = useState<RothExplorerResult | null>(null);
  const [isExploring, setIsExploring] = useState(false);
  const [strategy, setStrategy] = useState("bracket");
  const [targetRate, setTargetRate] = useState("0.24");

  async function runExplorer(apply: boolean) {
    setIsExploring(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        strategy,
        target_rate: targetRate,
        apply: String(apply)
      });
      const result = await apiRequest<RothExplorerResult>(
        `/scenarios/${params.id}/roth-explorer?${query.toString()}`,
        { method: "POST" }
      );
      setExplorer(result);
      if (apply) {
        await load();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Explorer failed");
    } finally {
      setIsExploring(false);
    }
  }

  async function load() {
    const [s, c] = await Promise.all([
      apiRequest<ScenarioDetail>(`/scenarios/${params.id}`),
      apiRequest<RothConversionPlan[]>(`/scenarios/${params.id}/roth-conversions`)
    ]);
    setScenario(s);
    setConversions(c);
  }

  useEffect(() => {
    load().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Unable to load");
    });
  }, [params.id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    setIsSaving(true);
    setError(null);
    const form = new FormData(formEl);
    const taxPaymentSource = String(form.get("taxPaymentSourceAccountId") ?? "");
    const payload = {
      source_account_id: String(form.get("sourceAccountId")),
      destination_account_id: String(form.get("destinationAccountId")),
      year: Number(form.get("year")),
      amount: String(form.get("amount")),
      tax_payment_source_account_id: taxPaymentSource || null
    };
    try {
      await apiRequest<RothConversionPlan>(`/scenarios/${params.id}/roth-conversions`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      formEl.reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteConversion(planId: string) {
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${params.id}/roth-conversions/${planId}`, {
        method: "DELETE"
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete");
    }
  }

  const accounts = scenario?.accounts ?? [];
  const traditionalAccounts = accounts.filter((a: Account) =>
    TRADITIONAL_TYPES.includes(a.account_type)
  );
  const rothAccounts = accounts.filter((a: Account) => ROTH_TYPES.includes(a.account_type));
  const cashAccounts = accounts.filter((a: Account) => a.account_type === "cash");
  const currentYear = new Date().getFullYear();

  if (!scenario) {
    return <main className="p-8 text-stone-600">Loading...</main>;
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[380px_1fr]">
        <aside className="flex flex-col gap-4">
          <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
            ← Back to scenario
          </Link>
          <form
            className="flex flex-col gap-4 rounded-md border border-stone-300 bg-white p-5"
            onSubmit={handleSubmit}
          >
            <h1 className="text-xl font-semibold text-stone-950">Add Roth conversion</h1>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Conversion year
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                defaultValue={currentYear}
                name="year"
                required
                type="number"
              />
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Source (traditional) account
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="sourceAccountId"
                required
              >
                <option value="">Select account…</option>
                {traditionalAccounts.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.account_type})
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Destination (Roth) account
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="destinationAccountId"
                required
              >
                <option value="">Select account…</option>
                {rothAccounts.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.account_type})
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Conversion amount ($)
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                min="0"
                name="amount"
                required
                step="1"
                type="number"
              />
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Tax payment source (optional, default cash)
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="taxPaymentSourceAccountId"
              >
                <option value="">Default (first cash account)</option>
                {cashAccounts.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>

            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add conversion"}
            </button>
          </form>
        </aside>

        <div className="flex flex-col gap-6">
        <section className="rounded-md border border-stone-300 bg-white p-5">
          <h2 className="text-xl font-semibold text-stone-950">Conversion Explorer</h2>
          <p className="mt-1 text-sm text-stone-500">
            Suggests a year-by-year conversion schedule that fills a target tax bracket (or stays
            under an IRMAA MAGI ceiling) and compares lifetime taxes and estate value.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Strategy
              <select
                className="h-10 rounded-md border border-stone-300 px-2"
                onChange={(e) => setStrategy(e.target.value)}
                value={strategy}
              >
                <option value="bracket">Fill tax bracket</option>
                <option value="irmaa">Stay under IRMAA</option>
              </select>
            </label>
            {strategy === "bracket" ? (
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Target bracket
                <select
                  className="h-10 rounded-md border border-stone-300 px-2"
                  onChange={(e) => setTargetRate(e.target.value)}
                  value={targetRate}
                >
                  <option value="0.10">10%</option>
                  <option value="0.12">12%</option>
                  <option value="0.22">22%</option>
                  <option value="0.24">24%</option>
                  <option value="0.32">32%</option>
                </select>
              </label>
            ) : null}
            <button
              className="h-10 rounded-md bg-stone-800 px-4 text-sm font-semibold text-white hover:bg-stone-900 disabled:opacity-60"
              disabled={isExploring}
              onClick={() => {
                void runExplorer(false);
              }}
              type="button"
            >
              {isExploring ? "Analyzing…" : "Explore"}
            </button>
          </div>

          {explorer ? (
            explorer.note ? (
              <p className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                {explorer.note}
              </p>
            ) : (
              <div className="mt-4 flex flex-col gap-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-md border border-stone-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-stone-500">Total converted</p>
                    <p className="text-lg font-semibold">
                      {formatMoney(explorer.total_converted)}
                    </p>
                  </div>
                  <div className="rounded-md border border-stone-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-stone-500">Lifetime tax</p>
                    <p className="text-lg font-semibold">
                      {formatMoney(explorer.baseline_lifetime_tax)} →{" "}
                      {formatMoney(explorer.projected_lifetime_tax)}
                    </p>
                  </div>
                  <div className="rounded-md border border-stone-200 p-3">
                    <p className="text-xs uppercase tracking-wide text-stone-500">Estate value</p>
                    <p className="text-lg font-semibold">
                      {formatMoney(explorer.baseline_estate)} →{" "}
                      {formatMoney(explorer.projected_estate)}
                    </p>
                  </div>
                </div>
                {explorer.suggestions.length > 0 ? (
                  <>
                    <div className="max-h-56 overflow-y-auto rounded-md border border-stone-200">
                      <table className="w-full text-sm">
                        <thead className="bg-stone-50 text-xs text-stone-500">
                          <tr>
                            <th className="px-3 py-2 text-left">Year</th>
                            <th className="px-3 py-2 text-right">Convert</th>
                            <th className="px-3 py-2 text-right">Headroom</th>
                          </tr>
                        </thead>
                        <tbody>
                          {explorer.suggestions.map((s) => (
                            <tr className="border-t border-stone-100" key={s.year}>
                              <td className="px-3 py-1.5">{s.year}</td>
                              <td className="px-3 py-1.5 text-right font-medium">
                                {formatMoney(s.amount)}
                              </td>
                              <td className="px-3 py-1.5 text-right text-stone-500">
                                {formatMoney(s.headroom)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <button
                      className="h-10 self-start rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
                      disabled={isExploring}
                      onClick={() => {
                        void runExplorer(true);
                      }}
                      type="button"
                    >
                      Apply these {explorer.suggestions.length} conversions
                    </button>
                  </>
                ) : (
                  <p className="text-sm text-stone-500">
                    No conversions suggested — no bracket headroom in the window.
                  </p>
                )}
              </div>
            )
          ) : null}
        </section>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">Roth conversion schedule</h2>
            <p className="mt-1 text-sm text-stone-500">
              {conversions.length} conversion{conversions.length !== 1 ? "s" : ""} scheduled
            </p>
          </div>
          {conversions.length === 0 ? (
            <p className="p-5 text-sm text-stone-500">No conversions scheduled.</p>
          ) : (
            <div className="divide-y divide-stone-200">
              {[...conversions]
                .sort((a, b) => a.year - b.year)
                .map((c) => {
                  const src = accounts.find((a: Account) => a.id === c.source_account_id);
                  const dst = accounts.find((a: Account) => a.id === c.destination_account_id);
                  return (
                    <div
                      className="grid gap-2 p-5 md:grid-cols-[80px_1fr_120px_80px]"
                      key={c.id}
                    >
                      <p className="font-semibold text-stone-950">{c.year}</p>
                      <div>
                        <p className="text-sm text-stone-800">
                          {src?.name ?? c.source_account_id} →{" "}
                          {dst?.name ?? c.destination_account_id}
                        </p>
                      </div>
                      <p className="font-semibold text-stone-950">{formatMoney(c.amount)}</p>
                      <button
                        className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                        onClick={() => {
                          void deleteConversion(c.id);
                        }}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  );
                })}
            </div>
          )}
        </section>
        </div>
      </div>
    </main>
  );
}
