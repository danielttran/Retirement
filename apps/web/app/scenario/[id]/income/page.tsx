"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, formatMoney, type IncomeStream, type ScenarioDetail } from "../../../lib/api";

const INCOME_KINDS = [
  "salary",
  "pension",
  "social_security",
  "annuity",
  "passive",
  "windfall",
  "other"
] as const;

const INFLATION_KINDS = ["cpi", "ss_cola", "pension_cola", "none", "custom"] as const;

export default function IncomePage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [streams, setStreams] = useState<IncomeStream[]>([]);
  const [selectedKind, setSelectedKind] = useState("salary");
  const [selectedInflation, setSelectedInflation] = useState("cpi");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function load() {
    const [s, inc] = await Promise.all([
      apiRequest<ScenarioDetail>(`/scenarios/${params.id}`),
      apiRequest<IncomeStream[]>(`/scenarios/${params.id}/income-streams`)
    ]);
    setScenario(s);
    setStreams(inc);
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
    const payload = {
      name: String(form.get("name")),
      kind,
      annual_amount: String(form.get("annualAmount")),
      start_year: Number(form.get("startYear")),
      end_year: form.get("endYear") ? Number(form.get("endYear")) : null,
      inflation_kind: String(form.get("inflationKind")),
      custom_inflation_rate:
        form.get("inflationKind") === "custom"
          ? String(Number(form.get("customInflationRate") ?? 0) / 100)
          : null,
      is_taxable_federal: form.get("isTaxableFederal") === "on",
      is_taxable_state: form.get("isTaxableState") === "on",
      claiming_age: kind === "social_security" ? Number(form.get("claimingAge")) : null,
      survivor_pct:
        kind === "pension" ? String(Number(form.get("survivorPct") ?? 0) / 100) : "0"
    };
    try {
      await apiRequest<IncomeStream>(`/scenarios/${params.id}/income-streams`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      formEl.reset();
      setSelectedKind("salary");
      setSelectedInflation("cpi");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteStream(streamId: string) {
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${params.id}/income-streams/${streamId}`, {
        method: "DELETE"
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete");
    }
  }

  const currentYear = new Date().getFullYear();

  if (!scenario) {
    return <main className="p-8 text-stone-600">Loading...</main>;
  }

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
            <h1 className="text-xl font-semibold text-stone-950">Add income stream</h1>
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
                onChange={(e) => setSelectedKind(e.target.value)}
                value={selectedKind}
              >
                {INCOME_KINDS.map((k) => (
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
                End year
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  name="endYear"
                  placeholder="lifetime"
                  type="number"
                />
              </label>
            </div>

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

            {selectedInflation === "custom" ? (
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Custom inflation rate %
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

            {selectedKind === "social_security" ? (
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Claiming age
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue="67"
                  name="claimingAge"
                  required
                  type="number"
                />
              </label>
            ) : null}

            {selectedKind === "pension" ? (
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Survivor benefit % (continues after owner&apos;s death)
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue="0"
                  max="100"
                  min="0"
                  name="survivorPct"
                  type="number"
                />
              </label>
            ) : null}

            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-sm font-medium text-stone-800">
                <input defaultChecked name="isTaxableFederal" type="checkbox" />
                Taxable federal
              </label>
              <label className="flex items-center gap-2 text-sm font-medium text-stone-800">
                <input defaultChecked name="isTaxableState" type="checkbox" />
                Taxable state
              </label>
            </div>

            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add stream"}
            </button>
          </form>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">Income streams</h2>
            <p className="mt-1 text-sm text-stone-500">{streams.length} saved</p>
          </div>
          {streams.length === 0 ? (
            <p className="p-5 text-sm text-stone-500">No income streams yet.</p>
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
