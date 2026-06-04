"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, formatMoney, type ExpenseStream } from "../../../lib/api";

const EXPENSE_KINDS = [
  "must_spend",
  "discretionary",
  "healthcare",
  "long_term_care",
  "one_time"
] as const;
const INFLATION_KINDS = ["cpi", "healthcare", "none", "custom"] as const;

export default function ExpensesPage() {
  const params = useParams<{ id: string }>();
  const [streams, setStreams] = useState<ExpenseStream[]>([]);
  const [selectedKind, setSelectedKind] = useState("must_spend");
  const [selectedInflation, setSelectedInflation] = useState("cpi");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function load() {
    setStreams(await apiRequest<ExpenseStream[]>(`/scenarios/${params.id}/expense-streams`));
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
    const kind = String(form.get("kind"));
    const isOneTime = kind === "one_time";
    const startYear = Number(form.get("startYear"));
    const payload = {
      name: String(form.get("name")),
      kind,
      annual_amount: String(form.get("annualAmount")),
      start_year: startYear,
      end_year: isOneTime ? startYear : form.get("endYear") ? Number(form.get("endYear")) : null,
      inflation_kind: isOneTime ? "none" : String(form.get("inflationKind")),
      custom_inflation_rate:
        !isOneTime && form.get("inflationKind") === "custom"
          ? String(Number(form.get("customInflationRate") ?? 0) / 100)
          : null
    };
    try {
      await apiRequest<ExpenseStream>(`/scenarios/${params.id}/expense-streams`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      formEl.reset();
      setSelectedKind("must_spend");
      setSelectedInflation("cpi");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save");
    } finally {
      setIsSaving(false);
    }
  }

  async function addMedicareEstimate(health: string) {
    setError(null);
    try {
      const est = await apiRequest<{ annual_per_person: string }>(
        `/calculators/medicare?health=${health}`
      );
      await apiRequest<ExpenseStream>(`/scenarios/${params.id}/expense-streams`, {
        method: "POST",
        body: JSON.stringify({
          name: `Medicare (${health}, est.)`,
          kind: "healthcare",
          annual_amount: est.annual_per_person,
          start_year: new Date().getFullYear(),
          inflation_kind: "healthcare"
        })
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add estimate");
    }
  }

  async function addAcaEstimate() {
    setError(null);
    try {
      const est = await apiRequest<{ annual_per_person: string }>(`/calculators/aca?age=60`);
      await apiRequest<ExpenseStream>(`/scenarios/${params.id}/expense-streams`, {
        method: "POST",
        body: JSON.stringify({
          name: "Pre-65 ACA (est.)",
          kind: "healthcare",
          annual_amount: est.annual_per_person,
          start_year: new Date().getFullYear(),
          inflation_kind: "healthcare"
        })
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add estimate");
    }
  }

  async function deleteStream(streamId: string) {
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${params.id}/expense-streams/${streamId}`, {
        method: "DELETE"
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete");
    }
  }

  const currentYear = new Date().getFullYear();
  const isOneTime = selectedKind === "one_time";

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[380px_1fr]">
        <aside className="flex flex-col gap-4">
          <Link
            className="text-sm font-semibold text-emerald-800"
            href={`/scenario/${params.id}`}
          >
            ← Back to scenario
          </Link>
          <form
            className="flex flex-col gap-4 rounded-md border border-stone-300 bg-white p-5"
            onSubmit={handleSubmit}
          >
            <h1 className="text-xl font-semibold text-stone-950">Add expense stream</h1>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Name
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                name="name"
                required
                type="text"
              />
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Kind
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="kind"
                onChange={(e) => {
                  setSelectedKind(e.target.value);
                  if (e.target.value === "healthcare") setSelectedInflation("healthcare");
                  else if (e.target.value === "one_time") setSelectedInflation("none");
                }}
                value={selectedKind}
              >
                {EXPENSE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Annual amount ($)
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                min="0"
                name="annualAmount"
                required
                step="1"
                type="number"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                {isOneTime ? "Year" : "Start year"}
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue={currentYear}
                  name="startYear"
                  required
                  type="number"
                />
              </label>
              {!isOneTime ? (
                <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                  End year
                  <input
                    className="h-10 rounded-md border border-stone-300 px-3"
                    name="endYear"
                    placeholder="lifetime"
                    type="number"
                  />
                </label>
              ) : null}
            </div>

            {!isOneTime ? (
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Inflation
                <select
                  className="h-10 rounded-md border border-stone-300 px-3"
                  name="inflationKind"
                  onChange={(e) => setSelectedInflation(e.target.value)}
                  value={selectedInflation}
                >
                  {INFLATION_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {selectedInflation === "custom" && !isOneTime ? (
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Custom rate %
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue="2.5"
                  name="customInflationRate"
                  required
                  step="0.01"
                  type="number"
                />
              </label>
            ) : null}

            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add expense"}
            </button>
          </form>

          <div className="flex flex-col gap-3 rounded-md border border-stone-300 bg-white p-5">
            <h2 className="text-base font-semibold text-stone-950">Medicare cost estimator</h2>
            <p className="text-sm text-stone-500">
              Add an estimated annual Medicare healthcare cost (premiums + supplement) by health
              status. IRMAA surcharges are added automatically based on income.
            </p>
            <div className="flex flex-wrap gap-2">
              {["excellent", "good", "poor"].map((h) => (
                <button
                  className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                  key={h}
                  onClick={() => {
                    void addMedicareEstimate(h);
                  }}
                  type="button"
                >
                  Add {h}
                </button>
              ))}
              <button
                className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                onClick={() => {
                  void addAcaEstimate();
                }}
                type="button"
              >
                Add pre-65 ACA
              </button>
            </div>
          </div>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">Expense streams</h2>
            <p className="mt-1 text-sm text-stone-500">{streams.length} saved</p>
          </div>
          {streams.length === 0 ? (
            <p className="p-5 text-sm text-stone-500">No expense streams yet.</p>
          ) : (
            <div className="divide-y divide-stone-200">
              {streams.map((s) => (
                <div
                  className="grid gap-2 p-5 md:grid-cols-[1fr_120px_100px_80px]"
                  key={s.id}
                >
                  <div>
                    <p className="font-semibold text-stone-950">{s.name}</p>
                    <p className="text-sm text-stone-500">
                      {s.kind} · {s.inflation_kind} inflation
                    </p>
                  </div>
                  <p className="font-semibold text-stone-950">{formatMoney(s.annual_amount)}/yr</p>
                  <p className="text-sm text-stone-500">
                    {s.start_year}–{s.end_year ?? "∞"}
                  </p>
                  <button
                    className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                    onClick={() => {
                      void deleteStream(s.id);
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
