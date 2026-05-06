"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useEffectEvent, useState } from "react";
import { useRouter } from "next/navigation";
import RunStatusBadge from "@/components/run-status-badge";
import { apiFetch } from "@/lib/api";
import type { Dataset, ListResponse, Run, Strategy } from "@/lib/types";

function formatDateTime(value?: string): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatSharpe(run: Run): string {
  const value = run.metrics?.sharpe_ratio;
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "-";
}

function formatReturn(run: Run): string {
  const value = run.metrics?.total_return;
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : "-";
}

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
  const [runs, setRuns] = useState<Run[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [datasetsError, setDatasetsError] = useState("");

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

  const loadRunHistory = useCallback(async () => {
    setRunsLoading(true);
    setRunsError("");

    try {
      const query = new URLSearchParams({ strategy_id: id, limit: "10" });
      const res = await apiFetch<ListResponse<Run>>(`/api/v1/runs?${query.toString()}`);
      setRuns(res.items);
    } catch (err) {
      setRunsError(err instanceof Error ? err.message : "Failed to load run history");
    } finally {
      setRunsLoading(false);
    }
  }, [id]);

  const loadDatasets = useCallback(async () => {
    setDatasetsLoading(true);
    setDatasetsError("");

    try {
      const res = await apiFetch<ListResponse<Dataset>>("/api/v1/datasets?limit=100");
      setDatasets(res.items);
      setSelectedDatasetId((current) => {
        if (current && res.items.some((dataset) => dataset.id === current)) return current;
        const aaplDataset = res.items.find(
          (dataset) => dataset.symbols.includes("AAPL") && dataset.timeframe === "1d"
        );
        return aaplDataset?.id ?? res.items[0]?.id ?? "";
      });
    } catch (err) {
      setDatasetsError(err instanceof Error ? err.message : "Failed to load datasets");
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStrategy();
    void loadRunHistory();
    void loadDatasets();
  }, [id, loadRunHistory, loadDatasets]);

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
        body: JSON.stringify({
          strategy_id: id,
          dataset_id: selectedDatasetId || undefined,
          params: {},
        }),
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
    <div className="mx-auto w-full max-w-5xl px-6 py-10">
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

        <div className="rounded border border-zinc-800 bg-zinc-900 p-4">
          <label className="block text-sm font-medium text-zinc-300">Dataset</label>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <select
              value={selectedDatasetId}
              onChange={(event) => setSelectedDatasetId(event.target.value)}
              disabled={datasetsLoading || datasets.length === 0}
              className="min-w-72 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none disabled:opacity-50"
            >
              {datasets.length === 0 ? (
                <option value="">Legacy sample fallback</option>
              ) : (
                datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name} - {dataset.symbols.join(", ")} - {dataset.timeframe}
                  </option>
                ))
              )}
            </select>
            <button
              onClick={() => void loadDatasets()}
              type="button"
              className="rounded border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
            >
              Refresh
            </button>
          </div>
          {datasetsError ? (
            <p className="mt-2 text-sm text-red-400">{datasetsError}</p>
          ) : (
            <p className="mt-2 text-xs text-zinc-500">
              {datasetsLoading
                ? "Loading registered datasets..."
                : selectedDatasetId
                  ? "This run will use the selected registered dataset."
                  : "No registered datasets were found; the worker will use the legacy sample fallback."}
            </p>
          )}
        </div>

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
            disabled={running || datasetsLoading}
            className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
          >
            {running ? "Starting..." : datasetsLoading ? "Loading datasets..." : "Run Backtest"}
          </button>
          <button
            onClick={handleDelete}
            className="rounded bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-600"
          >
            Delete
          </button>
        </div>
      </div>

      <section className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Run History</h2>
            <p className="mt-1 text-sm text-zinc-400">Latest backtests for this strategy.</p>
          </div>
          <button
            onClick={() => void loadRunHistory()}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Refresh
          </button>
        </div>

        {runsError ? (
          <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {runsError}
          </p>
        ) : null}

        {runsLoading ? (
          <p className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
            Loading run history...
          </p>
        ) : runs.length === 0 && !runsError ? (
          <div className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-5 text-sm">
            <p className="font-medium text-zinc-200">No runs for this strategy yet</p>
            <p className="mt-1 text-zinc-400">Start a backtest to create the first result.</p>
          </div>
        ) : runs.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-zinc-800 text-zinc-400">
                <tr>
                  <th className="pb-3 font-medium">Run</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Sharpe</th>
                  <th className="pb-3 font-medium">Return</th>
                  <th className="pb-3 font-medium">Completed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {runs.map((run) => (
                  <tr key={run.id} className="hover:bg-zinc-900">
                    <td className="py-3">
                      <Link href={`/runs/${run.id}`} className="text-blue-400 hover:underline">
                        Run {run.id.slice(0, 8)}...
                      </Link>
                    </td>
                    <td className="py-3">
                      <RunStatusBadge status={run.status} />
                    </td>
                    <td className="py-3 text-zinc-300">{formatSharpe(run)}</td>
                    <td className="py-3 text-zinc-300">{formatReturn(run)}</td>
                    <td className="py-3 text-zinc-400">
                      {formatDateTime(run.completed_at ?? run.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
