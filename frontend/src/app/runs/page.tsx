"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Run } from "@/lib/types";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-500/20 text-yellow-400",
  running: "bg-blue-500/20 text-blue-400",
  completed: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
};

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRuns();
  }, []);

  function loadRuns() {
    apiFetch<{ items: Run[]; total: number }>("/api/v1/runs")
      .then((res) => setRuns(res.items))
      .finally(() => setLoading(false));
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Runs</h1>
        <button
          onClick={loadRuns}
          className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <p className="mt-8 text-zinc-400">Loading...</p>
      ) : runs.length === 0 ? (
        <p className="mt-8 text-zinc-400">No runs yet. Run a backtest from a strategy page.</p>
      ) : (
        <table className="mt-8 w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-zinc-400">
            <tr>
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
                  <Link href={`/runs/${r.id}`} className="text-blue-400 hover:underline">
                    {r.strategy_id.slice(0, 8)}...
                  </Link>
                </td>
                <td className="py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[r.status] ?? ""}`}>
                    {r.status}
                  </span>
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
      )}
    </div>
  );
}
