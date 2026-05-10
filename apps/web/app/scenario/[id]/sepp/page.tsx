"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, formatMoney, type Account, type ScenarioDetail, type SeppPlan } from "../../../lib/api";

const METHODS = ["rmd", "fixed_amortization", "fixed_annuitization"] as const;
const STATUSES = ["planned", "active", "completed", "modified", "cancelled"] as const;

export default function SeppPage() {
  const params = useParams<{ id: string }>();
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [plans, setPlans] = useState<SeppPlan[]>([]);
  const [selectedMethod, setSelectedMethod] = useState("fixed_amortization");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function load() {
    const [s, p] = await Promise.all([
      apiRequest<ScenarioDetail>(`/scenarios/${params.id}`),
      apiRequest<SeppPlan[]>(`/scenarios/${params.id}/sepp-plans`)
    ]);
    setScenario(s);
    setPlans(p);
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
    const method = String(form.get("method"));
    const isFixed = method !== "rmd";
    const payload = {
      account_id: String(form.get("accountId")),
      method,
      status: String(form.get("status")),
      valuation_date: String(form.get("valuationDate")),
      first_payment_date: String(form.get("firstPaymentDate")),
      required_end_date: String(form.get("requiredEndDate")),
      age_at_first_payment: String(form.get("ageAtFirstPayment")),
      account_balance_at_valuation: String(form.get("accountBalanceAtValuation")),
      afr_prior_month: isFixed ? String(form.get("afrPriorMonth") ?? "0") : null,
      afr_two_months_prior: isFixed ? String(form.get("afrTwoMonthsPrior") ?? "0") : null,
      afr_month_used: isFixed ? "prior" : null,
      selected_interest_rate: isFixed ? String(Number(form.get("selectedRate") ?? 0) / 100) : null,
      max_allowed_interest_rate: null,
      initial_life_expectancy_factor: null,
      initial_annual_payment_locked: null,
      irs_notice_version: "Notice 2022-6",
      mortality_table_version: null,
      beneficiary_dob_snapshot: null,
      calculation_log_json: null,
      has_switched_to_rmd: false,
      switched_to_rmd_year: null
    };
    try {
      await apiRequest<SeppPlan>(`/scenarios/${params.id}/sepp-plans`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      formEl.reset();
      setSelectedMethod("fixed_amortization");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save");
    } finally {
      setIsSaving(false);
    }
  }

  async function deletePlan(planId: string) {
    setError(null);
    try {
      await apiRequest<void>(`/scenarios/${params.id}/sepp-plans/${planId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete");
    }
  }

  const accounts = scenario?.accounts ?? [];
  const today = new Date().toISOString().slice(0, 10);

  if (!scenario) {
    return <main className="p-8 text-stone-600">Loading...</main>;
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[400px_1fr]">
        <aside className="flex flex-col gap-4">
          <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
            ← Back to scenario
          </Link>
          <form
            className="flex flex-col gap-4 rounded-md border border-stone-300 bg-white p-5"
            onSubmit={handleSubmit}
          >
            <h1 className="text-xl font-semibold text-stone-950">Add SEPP / 72(t) plan</h1>
            {error ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                {error}
              </div>
            ) : null}

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Account
              <select className="h-10 rounded-md border border-stone-300 px-3" name="accountId" required>
                <option value="">Select account…</option>
                {accounts.map((a: Account) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.account_type})
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Method
              <select
                className="h-10 rounded-md border border-stone-300 px-3"
                name="method"
                onChange={(e) => setSelectedMethod(e.target.value)}
                value={selectedMethod}
              >
                {METHODS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Status
              <select className="h-10 rounded-md border border-stone-300 px-3" defaultValue="active" name="status">
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Valuation date
                <input className="h-10 rounded-md border border-stone-300 px-3" defaultValue={today} name="valuationDate" required type="date" />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                First payment date
                <input className="h-10 rounded-md border border-stone-300 px-3" defaultValue={today} name="firstPaymentDate" required type="date" />
              </label>
            </div>

            <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
              Required end date
              <input className="h-10 rounded-md border border-stone-300 px-3" name="requiredEndDate" required type="date" />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Age at first payment
                <input className="h-10 rounded-md border border-stone-300 px-3" name="ageAtFirstPayment" required step="0.1" type="number" />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                Account balance at valuation ($)
                <input className="h-10 rounded-md border border-stone-300 px-3" min="0" name="accountBalanceAtValuation" required step="0.01" type="number" />
              </label>
            </div>

            {selectedMethod !== "rmd" ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                    AFR prior month (decimal)
                    <input className="h-10 rounded-md border border-stone-300 px-3" defaultValue="0.05" name="afrPriorMonth" step="0.001" type="number" />
                  </label>
                  <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                    AFR 2 months prior (decimal)
                    <input className="h-10 rounded-md border border-stone-300 px-3" defaultValue="0.05" name="afrTwoMonthsPrior" step="0.001" type="number" />
                  </label>
                </div>
                <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
                  Selected interest rate %
                  <input className="h-10 rounded-md border border-stone-300 px-3" defaultValue="5" name="selectedRate" required step="0.01" type="number" />
                </label>
              </>
            ) : null}

            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
              disabled={isSaving}
              type="submit"
            >
              {isSaving ? "Saving..." : "Add SEPP plan"}
            </button>
          </form>
        </aside>

        <section className="rounded-md border border-stone-300 bg-white">
          <div className="border-b border-stone-200 px-5 py-4">
            <h2 className="text-xl font-semibold text-stone-950">SEPP plans</h2>
            <p className="mt-1 text-sm text-stone-500">{plans.length} saved</p>
          </div>
          {plans.length === 0 ? (
            <p className="p-5 text-sm text-stone-500">No SEPP plans yet.</p>
          ) : (
            <div className="divide-y divide-stone-200">
              {plans.map((plan) => {
                const acct = accounts.find((a: Account) => a.id === plan.account_id);
                return (
                  <div className="flex flex-col gap-2 p-5" key={plan.id}>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold text-stone-950">
                          {acct?.name ?? plan.account_id}
                        </p>
                        <p className="text-sm text-stone-500">
                          {plan.method} · {plan.status} · starts {plan.first_payment_date} · ends{" "}
                          {plan.required_end_date}
                        </p>
                        <p className="text-sm text-stone-500">
                          Balance at valuation:{" "}
                          {formatMoney(plan.account_balance_at_valuation)}
                          {plan.initial_annual_payment_locked
                            ? ` · Annual payment: ${formatMoney(plan.initial_annual_payment_locked)}`
                            : ""}
                        </p>
                      </div>
                      <button
                        className="h-9 rounded-md border border-stone-300 px-3 text-sm font-semibold text-stone-700 hover:bg-stone-100"
                        onClick={() => { void deletePlan(plan.id); }}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
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
