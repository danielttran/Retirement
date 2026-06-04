"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, type AssumptionSet } from "../../../lib/api";

export default function AssumptionsPage() {
  const params = useParams<{ id: string }>();
  const [assumptions, setAssumptions] = useState<AssumptionSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiRequest<AssumptionSet>(`/scenarios/${params.id}/assumptions`)
      .then(setAssumptions)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load");
      });
  }, [params.id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError(null);
    setSaved(false);
    const form = new FormData(event.currentTarget);
    const payload = {
      cpi_rate: String(Number(form.get("cpiRate") ?? 0) / 100),
      healthcare_inflation_rate: String(Number(form.get("healthcareRate") ?? 0) / 100),
      ss_cola_rate: String(Number(form.get("ssCola") ?? 0) / 100),
      pension_cola_rate: String(Number(form.get("pensionCola") ?? 0) / 100),
      housing_appreciation_rate: String(Number(form.get("housingRate") ?? 0) / 100),
      bracket_indexing_rate: String(Number(form.get("bracketIndexing") ?? 0) / 100),
      itemized_deductions: String(form.get("itemizedDeductions") ?? "0"),
      cash_reserve_target_months: Number(form.get("cashReserveMonths")),
      irs_data_version: String(form.get("irsDataVersion")),
      engine_version: assumptions?.engine_version ?? "0.1.0",
      state: String(form.get("state")),
      tax_iteration_max: Number(form.get("taxIterMax")),
      tax_iteration_tolerance: String(form.get("taxIterTolerance"))
    };
    try {
      const updated = await apiRequest<AssumptionSet>(
        `/scenarios/${params.id}/assumptions`,
        { method: "PUT", body: JSON.stringify(payload) }
      );
      setAssumptions(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save");
    } finally {
      setIsSaving(false);
    }
  }

  if (!assumptions) {
    return <main className="p-8 text-stone-600">Loading...</main>;
  }

  const pct = (v: string) => String(Number(v) * 100);

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto max-w-2xl flex flex-col gap-6">
        <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
          ← Back to scenario
        </Link>
        <form
          className="flex flex-col gap-5 rounded-md border border-stone-300 bg-white p-6"
          onSubmit={handleSubmit}
        >
          <h1 className="text-xl font-semibold text-stone-950">Assumptions</h1>

          {error ? (
            <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
              {error}
            </div>
          ) : null}
          {saved ? (
            <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
              Saved.
            </div>
          ) : null}

          <fieldset className="flex flex-col gap-4">
            <legend className="text-base font-semibold text-stone-950">Inflation rates</legend>

            {[
              { label: "CPI (general)", name: "cpiRate", default: pct(assumptions.cpi_rate) },
              {
                label: "Healthcare",
                name: "healthcareRate",
                default: pct(assumptions.healthcare_inflation_rate)
              },
              { label: "SS COLA", name: "ssCola", default: pct(assumptions.ss_cola_rate) },
              {
                label: "Pension COLA",
                name: "pensionCola",
                default: pct(assumptions.pension_cola_rate)
              },
              {
                label: "Housing appreciation",
                name: "housingRate",
                default: pct(assumptions.housing_appreciation_rate)
              },
              {
                label: "Bracket indexing",
                name: "bracketIndexing",
                default: pct(assumptions.bracket_indexing_rate)
              }
            ].map((field) => (
              <label key={field.name} className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
                <span>{field.label} %</span>
                <input
                  className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                  defaultValue={field.default}
                  name={field.name}
                  required
                  step="0.01"
                  type="number"
                />
              </label>
            ))}
          </fieldset>

          <hr className="border-stone-200" />

          <fieldset className="flex flex-col gap-4">
            <legend className="text-base font-semibold text-stone-950">Deductions</legend>
            <label className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
              Itemized deductions ($/yr, 0 = use standard)
              <input
                className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                defaultValue={assumptions.itemized_deductions}
                min="0"
                name="itemizedDeductions"
                step="1"
                type="number"
              />
            </label>
          </fieldset>

          <hr className="border-stone-200" />

          <fieldset className="flex flex-col gap-4">
            <legend className="text-base font-semibold text-stone-950">Cash management</legend>
            <label className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
              Cash reserve target (months)
              <input
                className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                defaultValue={assumptions.cash_reserve_target_months}
                min="0"
                name="cashReserveMonths"
                required
                type="number"
              />
            </label>
          </fieldset>

          <hr className="border-stone-200" />

          <fieldset className="flex flex-col gap-4">
            <legend className="text-base font-semibold text-stone-950">Tax engine</legend>
            <label className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
              IRS data version
              <input
                className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                defaultValue={assumptions.irs_data_version}
                name="irsDataVersion"
                required
                type="text"
              />
            </label>
            <label className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
              State
              <input
                className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                defaultValue={assumptions.state}
                name="state"
                required
                type="text"
              />
            </label>
            <label className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
              Tax iteration max
              <input
                className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                defaultValue={assumptions.tax_iteration_max}
                min="1"
                name="taxIterMax"
                required
                type="number"
              />
            </label>
            <label className="flex items-center justify-between gap-4 text-sm font-medium text-stone-800">
              Tax iteration tolerance ($)
              <input
                className="h-9 w-32 rounded-md border border-stone-300 px-3 text-right"
                defaultValue={assumptions.tax_iteration_tolerance}
                min="0"
                name="taxIterTolerance"
                required
                step="0.01"
                type="number"
              />
            </label>
          </fieldset>

          <button
            className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
            disabled={isSaving}
            type="submit"
          >
            {isSaving ? "Saving..." : "Save assumptions"}
          </button>
        </form>
      </div>
    </main>
  );
}
