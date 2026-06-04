"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, type ScenarioDetail } from "../../../lib/api";

export default function PeoplePage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function load() {
    setScenario(await apiRequest<ScenarioDetail>(`/scenarios/${params.id}`));
  }

  useEffect(() => {
    load().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : "Unable to load")
    );
  }, [params.id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scenario) return;
    const formEl = event.currentTarget;
    setIsSaving(true);
    setError(null);
    const form = new FormData(formEl);
    const deathAge = String(form.get("deathAge") ?? "");
    const payload = {
      name: String(form.get("name")),
      dob: String(form.get("dob")),
      life_expectancy_age: Number(form.get("lifeExpectancy")),
      death_age: deathAge ? Number(deathAge) : null
    };
    try {
      await apiRequest(`/households/${scenario.household_id}/people`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      formEl.reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add person");
    } finally {
      setIsSaving(false);
    }
  }

  async function deletePerson(personId: string) {
    if (!scenario) return;
    setError(null);
    try {
      await apiRequest(`/households/${scenario.household_id}/people/${personId}`, {
        method: "DELETE"
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete person");
    }
  }

  if (!scenario) {
    return <main className="p-8 text-stone-600">Loading…</main>;
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[360px_1fr]">
        <aside className="flex flex-col gap-4">
          <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
            ← Back to scenario
          </Link>
          <form
            className="flex flex-col gap-4 rounded-md border border-stone-300 bg-white p-5"
            onSubmit={handleSubmit}
          >
            <h1 className="text-xl font-semibold text-stone-950">Add spouse / partner</h1>
            <p className="text-sm text-stone-500">
              Adding a second person enables joint filing, Social Security survivor benefits, and
              death-of-spouse transitions.
            </p>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Name
              <input className="h-10 rounded-md border border-stone-300 px-3" name="name" required />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Date of birth
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                name="dob"
                required
                type="date"
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Life expectancy
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue="95"
                  name="lifeExpectancy"
                  required
                  type="number"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Death age (optional)
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  name="deathAge"
                  placeholder="= life exp."
                  type="number"
                />
              </label>
            </div>
            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add person"}
            </button>
          </form>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">
              People in {scenario.household.name}
            </h2>
          </div>
          <div className="divide-y divide-stone-200">
            {scenario.household.people.map((p) => (
              <div className="flex items-center justify-between p-5" key={p.id}>
                <div>
                  <p className="font-semibold text-stone-950">
                    {p.name}
                    {p.is_primary ? " (primary)" : ""}
                  </p>
                  <p className="text-sm text-stone-500">
                    Born {p.dob} · life expectancy {p.life_expectancy_age}
                    {p.death_age ? ` · dies at ${p.death_age}` : ""}
                  </p>
                </div>
                {!p.is_primary ? (
                  <button
                    className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                    onClick={() => {
                      void deletePerson(p.id);
                    }}
                    type="button"
                  >
                    Delete
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
