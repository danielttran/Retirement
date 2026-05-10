"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, type WithdrawalStrategy } from "../../../lib/api";

const VALID_STEPS = [
  "cash",
  "taxable_brokerage",
  "traditional",
  "roth_contributions",
  "roth_conversions_seasoned",
  "hsa",
  "roth_earnings"
];

export default function WithdrawalPage() {
  const params = useParams<{ id: string }>();
  const [strategy, setStrategy] = useState<WithdrawalStrategy | null>(null);
  const [order, setOrder] = useState<string[]>([]);
  const [surplusTarget, setSurplusTarget] = useState("taxable_brokerage");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiRequest<WithdrawalStrategy>(`/scenarios/${params.id}/withdrawal-strategy`)
      .then((s) => {
        setStrategy(s);
        setOrder(JSON.parse(s.order_json) as string[]);
        setSurplusTarget(s.surplus_target);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load");
      });
  }, [params.id]);

  function moveUp(index: number) {
    if (index === 0) return;
    const next = [...order];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    setOrder(next);
  }

  function moveDown(index: number) {
    if (index === order.length - 1) return;
    const next = [...order];
    [next[index], next[index + 1]] = [next[index + 1], next[index]];
    setOrder(next);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await apiRequest<WithdrawalStrategy>(
        `/scenarios/${params.id}/withdrawal-strategy`,
        {
          method: "PUT",
          body: JSON.stringify({ order_json: JSON.stringify(order), surplus_target: surplusTarget })
        }
      );
      setStrategy(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save");
    } finally {
      setIsSaving(false);
    }
  }

  if (!strategy) {
    return <main className="p-8 text-stone-600">Loading...</main>;
  }

  return (
    <main className="min-h-screen px-6 py-8">
      <div className="mx-auto max-w-xl flex flex-col gap-6">
        <Link className="text-sm font-semibold text-emerald-800" href={`/scenario/${params.id}`}>
          ← Back to scenario
        </Link>
        <form
          className="flex flex-col gap-5 rounded-md border border-stone-300 bg-white p-6"
          onSubmit={handleSubmit}
        >
          <h1 className="text-xl font-semibold text-stone-950">Withdrawal strategy</h1>

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

          <div className="flex flex-col gap-2">
            <p className="text-sm font-semibold text-stone-800">
              Drawdown order (drag or use arrows)
            </p>
            <ol className="flex flex-col gap-1">
              {order.map((step, i) => (
                <li
                  className="flex items-center gap-2 rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-sm font-medium text-stone-800"
                  key={step}
                >
                  <span className="w-5 text-right text-xs text-stone-400">{i + 1}.</span>
                  <span className="flex-1">{step}</span>
                  <button
                    className="h-7 w-7 rounded border border-stone-300 text-xs hover:bg-stone-200 disabled:opacity-40"
                    disabled={i === 0}
                    onClick={() => moveUp(i)}
                    type="button"
                  >
                    ↑
                  </button>
                  <button
                    className="h-7 w-7 rounded border border-stone-300 text-xs hover:bg-stone-200 disabled:opacity-40"
                    disabled={i === order.length - 1}
                    onClick={() => moveDown(i)}
                    type="button"
                  >
                    ↓
                  </button>
                </li>
              ))}
            </ol>
          </div>

          <label className="flex flex-col gap-1 text-sm font-medium text-stone-800">
            Surplus target account type
            <select
              className="h-10 rounded-md border border-stone-300 px-3"
              onChange={(e) => setSurplusTarget(e.target.value)}
              value={surplusTarget}
            >
              {VALID_STEPS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          <button
            className="inline-flex h-10 items-center justify-center rounded-md bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
            disabled={isSaving}
            type="submit"
          >
            {isSaving ? "Saving..." : "Save strategy"}
          </button>
        </form>
      </div>
    </main>
  );
}
