"use client";

import { use, useEffect, useEffectEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { Strategy, Run } from "@/lib/types";

export default function StrategyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const loadStrategy = useEffectEvent(async () => {
    setError("");

    try {
      const s = await apiFetch<Strategy>(`/api/v1/strategies/${id}`);
      setStrategy(s);
      setName(s.name);
      setDescription(s.description);
      setCode(s.code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load strategy");
    }
  });

  useEffect(() => {
    void loadStrategy();
  }, [id]);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const updated = await apiFetch<Strategy>(`/api/v1/strategies/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name, description, code }),
      });
      setStrategy(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleRun() {
    setRunning(true);
    setError("");
    try {
      const run = await apiFetch<Run>("/api/v1/runs", {
        method: "POST",
        body: JSON.stringify({ strategy_id: id, params: {} }),
      });
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
      setRunning(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this strategy? This cannot be undone.")) return;
    try {
      await apiFetch(`/api/v1/strategies/${id}`, { method: "DELETE" });
      router.push("/strategies");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  }

  if (!strategy) {
    return (
      <div className="px-6 py-10">
        <p className={error ? "text-red-400" : "text-zinc-400"}>{error || "Loading..."}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{strategy.name}</h1>
        <span className="text-sm text-zinc-400">v{strategy.version}</span>
      </div>

      <div className="mt-8 space-y-6">
        <div>
          <label className="block text-sm font-medium text-zinc-300">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-300">Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-300">Code</label>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={20}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
            spellCheck={false}
          />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
          >
            {running ? "Starting..." : "Run Backtest"}
          </button>
          <button
            onClick={handleDelete}
            className="rounded bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-600"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
