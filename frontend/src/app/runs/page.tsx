"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import RunStatusBadge from "@/components/run-status-badge";
import { apiFetch } from "@/lib/api";
import type { ListResponse, Run } from "@/lib/types";

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);

  useEffect(() => {
    void loadRuns();
  }, []);

  async function loadRuns() {
    setLoading(true);
    setError("");

    try {
      const res = await apiFetch<ListResponse<Run>>("/api/v1/runs");
      setRuns(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }

  function toggleRunSelection(runId: string) {
    setSelectedRunIds((current) =>
      current.includes(runId) ? current.filter((id) => id !== runId) : [...current, runId]
    );
  }

  function getCompareHref() {
    const query = new URLSearchParams({ runs: selectedRunIds.join(",") });
    return `/compare?${query.toString()}`;
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Runs</h1>
          {selectedRunIds.length > 0 ? (
            <p className="mt-1 text-sm text-zinc-400">
              {selectedRunIds.length} selected for comparison
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedRunIds.length >= 2 ? (
            <Link
              href={getCompareHref()}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
            >
              Compare selected
            </Link>
          ) : (
            <span className="rounded border border-zinc-800 px-3 py-1.5 text-sm text-zinc-500">
              Compare selected
            </span>
          )}
          <button
            onClick={loadRuns}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-8 text-zinc-400">Loading...</p>
      ) : runs.length === 0 && !error ? (
        <div className="mt-8 rounded border border-zinc-800 bg-zinc-900 p-5 text-sm">
          <p className="font-medium text-zinc-200">No runs yet</p>
          <p className="mt-1 text-zinc-400">Run a backtest from a strategy page to start building history.</p>
          <Link
            href="/strategies"
            className="mt-4 inline-flex rounded border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800"
          >
            View strategies
          </Link>
        </div>
      ) : runs.length > 0 ? (
        <table className="mt-8 w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-zinc-400">
            <tr>
              <th className="w-10 pb-3 font-medium"></th>
              <th className="pb-3 font-medium">Strategy</th>
              <th className="pb-3 font-medium">Status</th>
              <th className="pb-3 font-medium">Sharpe</th>
              <th className="pb-3 font-medium">Return</th>
              <th className="pb-3 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {runs.map((r) => (
              <tr key={r.id} className="hover:bg-zinc-900">
                <td className="py-3">
                  <input
                    type="checkbox"
                    checked={selectedRunIds.includes(r.id)}
                    onChange={() => toggleRunSelection(r.id)}
                    aria-label={`Select run ${r.id.slice(0, 8)} for comparison`}
                    className="h-4 w-4 rounded border-zinc-700 bg-zinc-950 accent-blue-600"
                  />
                </td>
                <td className="py-3">
                  <Link href={`/runs/${r.id}`} className="text-blue-400 hover:underline">
                    {r.strategy_id.slice(0, 8)}...
                  </Link>
                </td>
                <td className="py-3">
                  <RunStatusBadge status={r.status} />
                </td>
                <td className="py-3 text-zinc-300">
                  {r.metrics?.sharpe_ratio != null ? r.metrics.sharpe_ratio.toFixed(2) : "-"}
                </td>
                <td className="py-3 text-zinc-300">
                  {r.metrics?.total_return != null
                    ? `${(r.metrics.total_return * 100).toFixed(1)}%`
                    : "-"}
                </td>
                <td className="py-3 text-zinc-400">
                  {new Date(r.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
