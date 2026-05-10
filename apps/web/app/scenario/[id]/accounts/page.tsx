"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  apiRequest,
  formatMoney,
  formatPercent,
  type Account,
  type ScenarioDetail
} from "../../../lib/api";

const accountTypes = [
  "cash",
  "taxable_brokerage",
  "traditional_ira",
  "traditional_401k",
  "traditional_403b",
  "roth_ira",
  "roth_401k",
  "hsa",
  "governmental_457b",
  "real_estate",
  "debt"
];

export default function AccountsPage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [selectedType, setSelectedType] = useState("cash");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function loadScenario() {
    const nextScenario = await apiRequest<ScenarioDetail>(`/scenarios/${params.id}`);
    setScenario(nextScenario);
    setError(null);
  }

  useEffect(() => {
    loadScenario().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Unable to load accounts");
    });
  }, [params.id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!scenario) {
      return;
    }

    setIsSaving(true);
    setError(null);
    const form = new FormData(formElement);
    const payload = {
      owner_person_id: String(form.get("ownerPersonId")),
      name: String(form.get("name")),
      account_type: String(form.get("accountType")),
      current_balance: String(form.get("currentBalance")),
      expected_return: String(Number(form.get("expectedReturnPct") ?? 0) / 100),
      cost_basis_pct:
        selectedType === "taxable_brokerage"
          ? String(Number(form.get("costBasisPct") ?? 0) / 100)
          : null,
      roth_first_contribution_year:
        selectedType === "roth_ira" || selectedType === "roth_401k"
          ? Number(form.get("rothFirstContributionYear"))
          : null
    };

    try {
      await apiRequest<Account>(`/scenarios/${scenario.id}/accounts`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      formElement.reset();
      setSelectedType("cash");
      await loadScenario();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save account");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteAccount(accountId: string) {
    if (!scenario) {
      return;
    }
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${scenario.id}/accounts/${accountId}`, {
        method: "DELETE"
      });
      await loadScenario();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete account");
    }
  }

  if (!scenario) {
    return <main className="p-8 text-stone-600">Loading accounts...</main>;
  }

  const primaryPerson = scenario.household.people.find((person) => person.is_primary);

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[360px_1fr]">
        <aside className="flex flex-col gap-4">
          <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${scenario.id}`}>
            Back to scenario
          </Link>
          <form
            className="flex flex-col gap-4 rounded-md border border-stone-300 bg-white p-5"
            onSubmit={handleSubmit}
          >
            <h1 className="text-xl font-semibold text-stone-950">Add account</h1>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}

            <input name="ownerPersonId" type="hidden" value={primaryPerson?.id ?? ""} />

            <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
              Account name
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                name="name"
                required
                type="text"
              />
            </label>

            <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
              Type
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="accountType"
                onChange={(event) => setSelectedType(event.target.value)}
                value={selectedType}
              >
                {accountTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
              Current balance
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                name="currentBalance"
                required
                step="0.01"
                type="number"
              />
            </label>

            <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
              Expected annual return %
              <input
                className="h-10 rounded-md border border-stone-300 px-3"
                defaultValue="5"
                name="expectedReturnPct"
                required
                step="0.01"
                type="number"
              />
            </label>

            {selectedType === "taxable_brokerage" ? (
              <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
                Cost basis %
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  defaultValue="70"
                  name="costBasisPct"
                  required
                  step="0.01"
                  type="number"
                />
              </label>
            ) : null}

            {selectedType === "roth_ira" || selectedType === "roth_401k" ? (
              <label className="flex flex-col gap-2 text-sm font-medium text-stone-800">
                First Roth contribution year
                <input
                  className="h-10 rounded-md border border-stone-300 px-3"
                  name="rothFirstContributionYear"
                  required
                  type="number"
                />
              </label>
            ) : null}

            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving || !primaryPerson}
              type="submit"
            >
              {isSaving ? "Saving..." : "Save account"}
            </button>
          </form>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4">
            <div>
              <h2 className="text-xl font-semibold text-stone-950">{scenario.name} accounts</h2>
              <p className="mt-1 text-sm text-stone-600">
                Total balance {formatMoney(scenario.total_account_balance)}
              </p>
            </div>
          </div>

          {scenario.accounts.length === 0 ? (
            <p className="p-5 text-sm text-stone-600">No accounts saved yet.</p>
          ) : (
            <div className="divide-y divide-stone-200">
              {scenario.accounts.map((account) => (
                <div
                  className="grid gap-3 p-5 md:grid-cols-[1fr_160px_120px_80px]"
                  key={account.id}
                >
                  <div>
                    <p className="font-semibold text-stone-950">{account.name}</p>
                    <p className="text-sm text-stone-600">{account.account_type}</p>
                  </div>
                  <p className="font-semibold text-stone-950">
                    {formatMoney(account.current_balance)}
                  </p>
                  <p className="text-sm text-stone-600">{formatPercent(account.expected_return)}</p>
                  <button
                    className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                    onClick={() => {
                      void deleteAccount(account.id);
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
