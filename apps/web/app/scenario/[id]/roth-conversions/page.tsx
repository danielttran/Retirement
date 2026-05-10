"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  apiRequest,
  formatMoney,
  type Account,
  type RothConversionPlan,
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
    </main>
  );
}
