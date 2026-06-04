"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  apiRequest,
  formatMoney,
  type Account,
  type MoneyFlow,
  type ScenarioDetail
} from "../../../lib/api";

export default function MoneyFlowsPage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [flows, setFlows] = useState<MoneyFlow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function load() {
    const [s, f] = await Promise.all([
      apiRequest<ScenarioDetail>(`/scenarios/${params.id}`),
      apiRequest<MoneyFlow[]>(`/scenarios/${params.id}/money-flows`)
    ]);
    setScenario(s);
    setFlows(f);
  }

  useEffect(() => {
    load().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : "Unable to load")
    );
  }, [params.id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    setIsSaving(true);
    setError(null);
    const form = new FormData(formEl);
    const payload = {
      from_account_id: String(form.get("fromAccountId")),
      to_account_id: String(form.get("toAccountId")),
      year: Number(form.get("year")),
      amount: String(form.get("amount")),
      notes: String(form.get("notes") || "") || null
    };
    try {
      await apiRequest<MoneyFlow>(`/scenarios/${params.id}/money-flows`, {
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

  async function deleteFlow(id: string) {
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${params.id}/money-flows/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete");
    }
  }

  const accounts = scenario?.accounts ?? [];
  const currentYear = new Date().getFullYear();
  const acctName = (id: string) => accounts.find((a: Account) => a.id === id)?.name ?? id;

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
            <h1 className="text-xl font-semibold text-stone-950">Add money flow</h1>
            <p className="text-sm text-stone-500">
              Move money between accounts in a specific year — reallocate savings, pay down debt, or
              take an early withdrawal. Pre-tax sources are taxed as ordinary income; brokerage
              sources realize capital gains.
            </p>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              From account
              <select className="h-10 rounded-md border border-stone-300 px-3" name="fromAccountId" required>
                <option value="">Select…</option>
                {accounts.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.account_type})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              To account (debt account = pay down)
              <select className="h-10 rounded-md border border-stone-300 px-3" name="toAccountId" required>
                <option value="">Select…</option>
                {accounts.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.account_type})
                  </option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Year
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue={currentYear}
                  name="year"
                  required
                  type="number"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Amount ($)
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  min="0"
                  name="amount"
                  required
                  type="number"
                />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Notes (optional)
              <input className="h-10 rounded-md border border-stone-300 px-3" name="notes" />
            </label>
            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add money flow"}
            </button>
          </form>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">Scheduled money flows</h2>
            <p className="mt-1 text-sm text-stone-500">{flows.length} scheduled</p>
          </div>
          {flows.length === 0 ? (
            <p className="p-5 text-sm text-stone-500">No money flows scheduled.</p>
          ) : (
            <div className="divide-y divide-stone-200">
              {[...flows]
                .sort((a, b) => a.year - b.year)
                .map((f) => (
                  <div className="grid gap-2 p-5 md:grid-cols-[70px_1fr_120px_70px]" key={f.id}>
                    <p className="font-semibold text-stone-950">{f.year}</p>
                    <p className="text-sm text-stone-800">
                      {acctName(f.from_account_id)} → {acctName(f.to_account_id)}
                      {f.notes ? <span className="text-stone-400"> · {f.notes}</span> : null}
                    </p>
                    <p className="font-semibold text-stone-950">{formatMoney(f.amount)}</p>
                    <button
                      className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                      onClick={() => {
                        void deleteFlow(f.id);
                      }}
                      type="button"
                    >
                      Delete
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
