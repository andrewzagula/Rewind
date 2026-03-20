"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Strategy } from "@/lib/types";

const DEFAULT_CODE = `from engine.strategy import Strategy
from engine.signal import Signal


class MyStrategy(Strategy):
    def init(self, params):
        pass

    def next(self, row, portfolio):
        return None
`;

export default function NewStrategyPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState(DEFAULT_CODE);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const strategy = await apiFetch<Strategy>("/api/v1/strategies", {
        method: "POST",
        body: JSON.stringify({ name, description, code }),
      });
      router.push(`/strategies/${strategy.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create strategy");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold">New Strategy</h1>

      <form onSubmit={handleSubmit} className="mt-8 space-y-6">
        <div>
          <label className="block text-sm font-medium text-zinc-300">Name</label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
            placeholder="e.g. BuyAndHold"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-300">Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
            placeholder="Brief description of the strategy"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-300">Code</label>
          <textarea
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={20}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
            spellCheck={false}
          />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {submitting ? "Creating..." : "Create Strategy"}
        </button>
      </form>
    </div>
  );
}
