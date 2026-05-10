"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { apiRequest, type ScenarioDetail } from "../../lib/api";

export default function NewHouseholdPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError(null);

    const form = new FormData(event.currentTarget);
    const payload = {
      name: String(form.get("householdName") ?? ""),
      filing_status: String(form.get("filingStatus") ?? "single"),
      state: "MA",
      scenario_name: String(form.get("scenarioName") ?? "Baseline"),
      primary_person: {
        name: String(form.get("personName") ?? ""),
        dob: String(form.get("dob") ?? ""),
        retirement_date: String(form.get("retirementDate") ?? "") || null,
        life_expectancy_age: Number(form.get("lifeExpectancyAge") ?? 95)
      }
    };

    try {
      const scenario = await apiRequest<ScenarioDetail>("/households", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      router.push(`/scenario/${scenario.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create household");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <form className="mx-auto flex max-w-3xl flex-col gap-7" onSubmit={handleSubmit}>
        <header className="border-b border-stone-300 pb-5">
          <p className="text-sm font-medium uppercase tracking-wide text-emerald-700">
            Household setup
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-stone-950">Create a household</h1>
        </header>

        {error ? (
          <div className="rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-900">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4 rounded-md border border-stone-300 bg-white p-5 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Household name
            <input
              className="h-11 rounded-md border border-stone-300 px-3 text-base"
              name="householdName"
              required
              type="text"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Filing status
            <select className="h-11 rounded-md border border-stone-300 px-3" name="filingStatus">
              <option value="single">Single</option>
              <option value="mfj">Married filing jointly</option>
              <option value="mfs">Married filing separately</option>
              <option value="hoh">Head of household</option>
              <option value="qw">Qualifying widow(er)</option>
            </select>
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Scenario name
            <input
              className="h-11 rounded-md border border-stone-300 px-3 text-base"
              defaultValue="Baseline"
              name="scenarioName"
              required
              type="text"
            />
          </label>
        </section>

        <section className="grid gap-4 rounded-md border border-stone-300 bg-white p-5 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Primary person
            <input
              className="h-11 rounded-md border border-stone-300 px-3 text-base"
              name="personName"
              required
              type="text"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Date of birth
            <input
              className="h-11 rounded-md border border-stone-300 px-3 text-base"
              name="dob"
              required
              type="date"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Retirement date
            <input
              className="h-11 rounded-md border border-stone-300 px-3 text-base"
              name="retirementDate"
              type="date"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
            Life expectancy age
            <input
              className="h-11 rounded-md border border-stone-300 px-3 text-base"
              defaultValue="95"
              max="130"
              min="1"
              name="lifeExpectancyAge"
              required
              type="number"
            />
          </label>
        </section>

        <div className="flex justify-end">
          <button
            className="inline-flex h-11 items-center justify-center rounded-md bg-emerald-700 px-5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-60"
            disabled={isSaving}
            type="submit"
          >
            {isSaving ? "Saving..." : "Create baseline scenario"}
          </button>
        </div>
      </form>
    </main>
  );
}

