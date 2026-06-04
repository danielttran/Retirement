"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  apiRequest,
  formatMoney,
  type Account,
  type Contribution,
  type ScenarioDetail
} from "../../../lib/api";

// Account types you can contribute to during the accumulation phase.
const CONTRIBUTABLE_TYPES = [
  "traditional_401k",
  "traditional_403b",
  "governmental_457b",
  "traditional_ira",
  "roth_ira",
  "roth_401k",
  "hsa",
  "taxable_brokerage",
  "cash"
];

const PRETAX_TYPES = [
  "traditional_401k",
  "traditional_403b",
  "governmental_457b",
  "traditional_ira",
  "hsa"
];

export default function ContributionsPage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [contributions, setContributions] = useState<Contribution[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function load() {
    const [s, c] = await Promise.all([
      apiRequest<ScenarioDetail>(`/scenarios/${params.id}`),
      apiRequest<Contribution[]>(`/scenarios/${params.id}/contributions`)
    ]);
    setScenario(s);
    setContributions(c);
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
    const endYear = String(form.get("endYear") ?? "");
    const payload = {
      account_id: String(form.get("accountId")),
      annual_amount: String(form.get("annualAmount")),
      start_year: Number(form.get("startYear")),
      end_year: endYear ? Number(endYear) : null,
      inflation_kind: String(form.get("inflationKind")),
      employer_match_amount: String(form.get("employerMatch") || "0")
    };
    try {
      await apiRequest<Contribution>(`/scenarios/${params.id}/contributions`, {
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

  async function deleteContribution(id: string) {
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${params.id}/contributions/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete");
    }
  }

  const accounts = scenario?.accounts ?? [];
  const contributable = accounts.filter((a: Account) =>
    CONTRIBUTABLE_TYPES.includes(a.account_type)
  );
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
            <h1 className="text-xl font-semibold text-stone-950">Add contribution</h1>
            <p className="text-sm text-stone-500">
              Recurring savings into an account while working. Pre-tax contributions (401k, 403b,
              457b, traditional IRA, HSA) reduce taxable income. Employer match is added on top.
            </p>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Account
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="accountId"
                required
              >
                <option value="">Select account…</option>
                {contributable.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.account_type})
                    {PRETAX_TYPES.includes(a.account_type) ? " · pre-tax" : ""}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Annual employee contribution ($)
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                min="0"
                name="annualAmount"
                required
                step="1"
                type="number"
              />
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Employer match ($/yr, optional)
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                defaultValue="0"
                min="0"
                name="employerMatch"
                step="1"
                type="number"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Start year
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue={currentYear}
                  name="startYear"
                  required
                  type="number"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                End year (blank = until retirement)
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  name="endYear"
                  type="number"
                />
              </label>
            </div>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Growth of contribution
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                defaultValue="cpi"
                name="inflationKind"
              >
                <option value="cpi">Grow with CPI</option>
                <option value="none">Flat (no growth)</option>
              </select>
            </label>

            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add contribution"}
            </button>
          </form>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">Contribution schedule</h2>
            <p className="mt-1 text-sm text-stone-500">
              {contributions.length} contribution{contributions.length !== 1 ? "s" : ""}
            </p>
          </div>
          {contributions.length === 0 ? (
            <p className="p-5 text-sm text-stone-500">
              No contributions yet. Add 401(k)/IRA/HSA savings to model the accumulation phase.
            </p>
          ) : (
            <div className="divide-y divide-stone-200">
              {[...contributions]
                .sort((a, b) => a.start_year - b.start_year)
                .map((c) => {
                  const acct = accounts.find((a: Account) => a.id === c.account_id);
                  const match = Number(c.employer_match_amount);
                  return (
                    <div
                      className="grid gap-2 p-5 md:grid-cols-[1fr_140px_120px_80px]"
                      key={c.id}
                    >
                      <div>
                        <p className="text-sm font-semibold text-stone-900">
                          {acct?.name ?? c.account_id}
                        </p>
                        <p className="text-xs text-stone-500">
                          {c.start_year}–{c.end_year ?? "retirement"}
                          {match > 0 ? ` · +${formatMoney(match)} match` : ""}
                        </p>
                      </div>
                      <p className="font-semibold text-stone-950">
                        {formatMoney(c.annual_amount)}/yr
                      </p>
                      <p className="text-sm text-stone-500">
                        {c.inflation_kind === "none" ? "flat" : "CPI-indexed"}
                      </p>
                      <button
                        className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                        onClick={() => {
                          void deleteContribution(c.id);
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
