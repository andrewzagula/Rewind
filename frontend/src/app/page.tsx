"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import RunStatusBadge from "@/components/run-status-badge";
import { apiFetch } from "@/lib/api";
import type { ListResponse, Run, Strategy } from "@/lib/types";

const RUN_LIMIT = 25;
const STRATEGY_LIMIT = 8;

function getNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatSharpe(value: unknown): string {
  const number = getNumber(value);
  return number == null ? "-" : number.toFixed(2);
}

function formatPercent(value: unknown): string {
  const number = getNumber(value);
  return number == null ? "-" : `${(number * 100).toFixed(1)}%`;
}

function formatDateTime(value?: string): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleDateString() : "-";
}

function isCompletedWithSharpe(run: Run): boolean {
  return run.status === "completed" && getNumber(run.metrics?.sharpe_ratio) != null;
}

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyTotal, setStrategyTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");

    try {
      const [runRes, strategyRes] = await Promise.all([
        apiFetch<ListResponse<Run>>(`/api/v1/runs?limit=${RUN_LIMIT}`),
        apiFetch<ListResponse<Strategy>>(`/api/v1/strategies?limit=${STRATEGY_LIMIT}`),
      ]);
      setRuns(runRes.items);
      setRunTotal(runRes.total);
      setStrategies(strategyRes.items);
      setStrategyTotal(strategyRes.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const completedRuns = useMemo(
    () => runs.filter((run) => run.status === "completed"),
    [runs]
  );
  const failedRuns = useMemo(
    () => runs.filter((run) => run.status === "failed").slice(0, 5),
    [runs]
  );
  const bestRuns = useMemo(
    () =>
      runs
        .filter(isCompletedWithSharpe)
        .sort((a, b) => {
          const aSharpe = getNumber(a.metrics?.sharpe_ratio) ?? Number.NEGATIVE_INFINITY;
          const bSharpe = getNumber(b.metrics?.sharpe_ratio) ?? Number.NEGATIVE_INFINITY;
          return bSharpe - aSharpe;
        })
        .slice(0, 5),
    [runs]
  );
  const activeRunCount = runs.filter((run) => run.status === "pending" || run.status === "running").length;

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Research Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-400">Recent experiments and strategy activity.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => void loadDashboard()}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Refresh
          </button>
          <Link
            href="/strategies/new"
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
          >
            New Strategy
          </Link>
          <Link
            href="/runs"
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Runs
          </Link>
        </div>
      </header>

      {error ? (
        <p className="mt-6 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="mt-8 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
          Loading dashboard...
        </p>
      ) : (
        <>
          <section className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryTile label="Strategies" value={strategyTotal.toLocaleString()} />
            <SummaryTile label="Runs" value={runTotal.toLocaleString()} />
            <SummaryTile label="Completed" value={completedRuns.length.toLocaleString()} />
            <SummaryTile label="Active" value={activeRunCount.toLocaleString()} />
          </section>

          <div className="mt-8 grid gap-8 lg:grid-cols-[1.25fr_1fr]">
            <section>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Recent Runs</h2>
                <Link href="/runs" className="text-sm text-blue-400 hover:underline">
                  View all
                </Link>
              </div>
              {runs.length === 0 ? (
                <EmptyPanel
                  title="No runs yet"
                  message="Run a backtest from a strategy page to start tracking experiments."
                  href="/strategies"
                  action="View strategies"
                />
              ) : (
                <RunTable runs={runs.slice(0, 8)} />
              )}
            </section>

            <section>
              <h2 className="text-lg font-semibold">Recent Strategies</h2>
              {strategies.length === 0 ? (
                <EmptyPanel
                  title="No strategies yet"
                  message="Create a strategy before launching the first backtest."
                  href="/strategies/new"
                  action="New strategy"
                />
              ) : (
                <div className="mt-4 divide-y divide-zinc-800 overflow-hidden rounded border border-zinc-800">
                  {strategies.map((strategy) => (
                    <Link
                      key={strategy.id}
                      href={`/strategies/${strategy.id}`}
                      className="block bg-zinc-900 px-4 py-3 hover:bg-zinc-800"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-sm font-medium text-zinc-100">{strategy.name}</p>
                        <span className="shrink-0 text-xs text-zinc-500">v{strategy.version}</span>
                      </div>
                      <p className="mt-1 text-xs text-zinc-500">
                        Updated {formatDate(strategy.updated_at)}
                      </p>
                    </Link>
                  ))}
                </div>
              )}
            </section>

            <section>
              <h2 className="text-lg font-semibold">Best Completed Runs</h2>
              {bestRuns.length === 0 ? (
                <EmptyPanel title="No completed runs with Sharpe yet" message="Completed run metrics will appear here." />
              ) : (
                <RunTable runs={bestRuns} />
              )}
            </section>

            <section>
              <h2 className="text-lg font-semibold">Failed Runs</h2>
              {failedRuns.length === 0 ? (
                <EmptyPanel title="No failed runs" message="Recent run failures will appear here." />
              ) : (
                <div className="mt-4 divide-y divide-zinc-800 overflow-hidden rounded border border-zinc-800">
                  {failedRuns.map((run) => (
                    <Link
                      key={run.id}
                      href={`/runs/${run.id}`}
                      className="block bg-zinc-900 px-4 py-3 hover:bg-zinc-800"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium text-blue-400">Run {run.id.slice(0, 8)}...</span>
                        <RunStatusBadge status={run.status} />
                      </div>
                      <p className="mt-2 break-words text-xs text-red-300">
                        {run.error || "No error details were stored."}
                      </p>
                    </Link>
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-xs text-zinc-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-zinc-100">{value}</p>
    </div>
  );
}

function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-zinc-800 text-zinc-400">
          <tr>
            <th className="pb-3 font-medium">Run</th>
            <th className="pb-3 font-medium">Status</th>
            <th className="pb-3 font-medium">Sharpe</th>
            <th className="pb-3 font-medium">Return</th>
            <th className="pb-3 font-medium">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {runs.map((run) => (
            <tr key={run.id} className="hover:bg-zinc-900">
              <td className="py-3">
                <Link href={`/runs/${run.id}`} className="text-blue-400 hover:underline">
                  Run {run.id.slice(0, 8)}...
                </Link>
                <div className="mt-0.5 text-xs text-zinc-500">
                  Strategy {run.strategy_id.slice(0, 8)}...
                </div>
              </td>
              <td className="py-3">
                <RunStatusBadge status={run.status} />
              </td>
              <td className="py-3 text-zinc-300">{formatSharpe(run.metrics?.sharpe_ratio)}</td>
              <td className="py-3 text-zinc-300">{formatPercent(run.metrics?.total_return)}</td>
              <td className="py-3 text-zinc-400">{formatDateTime(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmptyPanel({
  title,
  message,
  href,
  action,
}: {
  title: string;
  message: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-5 text-sm">
      <p className="font-medium text-zinc-200">{title}</p>
      <p className="mt-1 text-zinc-400">{message}</p>
      {href && action ? (
        <Link
          href={href}
          className="mt-4 inline-flex rounded border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800"
        >
          {action}
        </Link>
      ) : null}
    </div>
  );
}
