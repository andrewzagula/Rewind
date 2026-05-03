"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import RunStatusBadge from "@/components/run-status-badge";
import { apiFetch } from "@/lib/api";
import type { CompareResponse, ComparedRun, ListResponse, MetricDelta, Run } from "@/lib/types";

const RUN_LIMIT = 50;
const RUN_COLORS = ["#3b82f6", "#22c55e", "#f97316", "#a855f7", "#eab308", "#14b8a6"];

const metricFormatters: Record<string, { label: string; format: (value: number) => string }> = {
  total_return: { label: "Total Return", format: (value) => `${(value * 100).toFixed(2)}%` },
  annualized_return: {
    label: "Annualized Return",
    format: (value) => `${(value * 100).toFixed(2)}%`,
  },
  sharpe_ratio: { label: "Sharpe Ratio", format: (value) => value.toFixed(3) },
  sortino_ratio: { label: "Sortino Ratio", format: (value) => value.toFixed(3) },
  max_drawdown: { label: "Max Drawdown", format: (value) => `${(value * 100).toFixed(2)}%` },
  calmar_ratio: { label: "Calmar Ratio", format: (value) => value.toFixed(3) },
  volatility_annual: {
    label: "Annual Volatility",
    format: (value) => `${(value * 100).toFixed(2)}%`,
  },
  total_trades: { label: "Total Trades", format: (value) => value.toLocaleString() },
  win_rate: { label: "Win Rate", format: (value) => `${(value * 100).toFixed(1)}%` },
  profit_factor: { label: "Profit Factor", format: (value) => value.toFixed(2) },
  avg_trade_pnl: { label: "Avg Trade PnL", format: (value) => formatCurrency(value) },
  avg_win: { label: "Avg Win", format: (value) => formatCurrency(value) },
  avg_loss: { label: "Avg Loss", format: (value) => formatCurrency(value) },
};

type EquitySeries = {
  run: ComparedRun;
  key: string;
  color: string;
};

function parseRunsParam(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(",")
    .map((id) => id.trim())
    .filter((id) => {
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
}

function comparePath(runIds: string[]): string {
  if (runIds.length === 0) return "/compare";
  const query = new URLSearchParams({ runs: runIds.join(",") });
  return `/compare?${query.toString()}`;
}

function formatCurrency(value: number | unknown): string {
  return `$${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatDateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatMetricValue(key: string, value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return metricFormatters[key]?.format(value) ?? value.toFixed(3);
}

function formatMetricDelta(key: string, value: number | null | undefined, isBase: boolean): string {
  if (isBase) return "Baseline";
  if (value == null || !Number.isFinite(value)) return "-";
  const formatted = formatMetricValue(key, Math.abs(value));
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${formatted}`;
}

function metricLabel(key: string): string {
  return metricFormatters[key]?.label ?? key.replaceAll("_", " ");
}

function runLabel(run: Pick<Run, "id">): string {
  return `Run ${run.id.slice(0, 8)}...`;
}

function buildEquityOverlay(runs: ComparedRun[]) {
  const series: EquitySeries[] = runs
    .map((run, index) => ({ run, index }))
    .filter(({ run }) => run.status === "completed" && run.equity_points.length > 0)
    .map(({ run, index }) => ({
      run,
      key: `run_${index}`,
      color: RUN_COLORS[index % RUN_COLORS.length],
    }));

  const rows = new Map<number, Record<string, number>>();
  series.forEach((item) => {
    item.run.equity_points.forEach((point) => {
      const day = point.index + 1;
      const row = rows.get(day) ?? { day };
      row[item.key] = point.value;
      rows.set(day, row);
    });
  });

  return {
    series,
    data: Array.from(rows.values()).sort((a, b) => a.day - b.day),
  };
}

export default function ComparePageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const runsParam = searchParams.get("runs") ?? "";
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>(() => parseRunsParam(runsParam));
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const [compare, setCompare] = useState<CompareResponse | null>(null);
  const [runsLoading, setRunsLoading] = useState(true);
  const [compareLoading, setCompareLoading] = useState(false);
  const [runsError, setRunsError] = useState("");
  const [compareError, setCompareError] = useState("");

  useEffect(() => {
    setSelectedRunIds(parseRunsParam(runsParam));
  }, [runsParam]);

  useEffect(() => {
    async function loadRecentRuns() {
      setRunsLoading(true);
      setRunsError("");

      try {
        const res = await apiFetch<ListResponse<Run>>(`/api/v1/runs?limit=${RUN_LIMIT}`);
        setRecentRuns(res.items);
      } catch (err) {
        setRunsError(err instanceof Error ? err.message : "Failed to load recent runs");
      } finally {
        setRunsLoading(false);
      }
    }

    void loadRecentRuns();
  }, []);

  useEffect(() => {
    let active = true;

    async function loadComparison() {
      if (selectedRunIds.length < 2) {
        setCompare(null);
        setCompareError("");
        return;
      }

      setCompareLoading(true);
      setCompareError("");

      try {
        const query = new URLSearchParams({ run_ids: selectedRunIds.join(",") });
        const res = await apiFetch<CompareResponse>(`/api/v1/compare?${query.toString()}`);
        if (active) setCompare(res);
      } catch (err) {
        if (active) {
          setCompare(null);
          setCompareError(err instanceof Error ? err.message : "Failed to load comparison");
        }
      } finally {
        if (active) setCompareLoading(false);
      }
    }

    void loadComparison();
    return () => {
      active = false;
    };
  }, [selectedRunIds]);

  const selectedSet = useMemo(() => new Set(selectedRunIds), [selectedRunIds]);

  function updateSelection(runId: string) {
    const next = selectedSet.has(runId)
      ? selectedRunIds.filter((id) => id !== runId)
      : [...selectedRunIds, runId];
    setSelectedRunIds(next);
    router.replace(comparePath(next), { scroll: false });
  }

  const overlay = useMemo(() => buildEquityOverlay(compare?.runs ?? []), [compare]);

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Run Comparison</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Compare metrics and equity curves against the first selected run.
          </p>
        </div>
        <Link
          href="/runs"
          className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
        >
          Runs
        </Link>
      </header>

      <section className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Run Picker</h2>
            <p className="mt-1 text-sm text-zinc-400">
              {selectedRunIds.length} selected from recent runs
            </p>
          </div>
          {selectedRunIds.length > 0 ? (
            <button
              onClick={() => {
                setSelectedRunIds([]);
                router.replace("/compare", { scroll: false });
              }}
              className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
            >
              Clear
            </button>
          ) : null}
        </div>

        {runsError ? (
          <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {runsError}
          </p>
        ) : null}

        {runsLoading ? (
          <p className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
            Loading recent runs...
          </p>
        ) : recentRuns.length === 0 ? (
          <EmptyPanel message="No runs are available yet. Start a backtest from a strategy page first." />
        ) : (
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {recentRuns.map((run) => (
              <label
                key={run.id}
                className={`flex cursor-pointer items-start gap-3 rounded border p-3 text-sm ${
                  selectedSet.has(run.id)
                    ? "border-blue-500 bg-blue-950/30"
                    : "border-zinc-800 bg-zinc-900 hover:bg-zinc-800"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedSet.has(run.id)}
                  onChange={() => updateSelection(run.id)}
                  className="mt-0.5 h-4 w-4 rounded border-zinc-700 bg-zinc-950 accent-blue-600"
                />
                <span className="min-w-0">
                  <span className="block font-medium text-zinc-100">{runLabel(run)}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-2">
                    <RunStatusBadge status={run.status} />
                    <span className="text-xs text-zinc-500">
                      {formatDateTime(run.completed_at ?? run.created_at)}
                    </span>
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </section>

      {selectedRunIds.length < 2 ? (
        <EmptyPanel message="Select at least two runs to compare metrics and equity curves." />
      ) : compareLoading ? (
        <EmptyPanel message="Loading comparison..." />
      ) : compareError ? (
        <p className="mt-8 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          {compareError}
        </p>
      ) : compare ? (
        <>
          <RunSummary runs={compare.runs} />
          <MetricComparison runs={compare.runs} deltas={compare.metric_deltas} />
          <EquityOverlay overlay={overlay} />
        </>
      ) : null}
    </div>
  );
}

function RunSummary({ runs }: { runs: ComparedRun[] }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">Selected Runs</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-zinc-800 text-zinc-400">
            <tr>
              <th className="pb-3 font-medium">Run</th>
              <th className="pb-3 font-medium">Status</th>
              <th className="pb-3 font-medium">Symbol</th>
              <th className="pb-3 font-medium">Timeframe</th>
              <th className="pb-3 font-medium">Initial Cash</th>
              <th className="pb-3 font-medium">Completed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {runs.map((run, index) => (
              <tr key={run.id} className="hover:bg-zinc-900">
                <td className="py-3">
                  <Link href={`/runs/${run.id}`} className="text-blue-400 hover:underline">
                    {index === 0 ? `${runLabel(run)} baseline` : runLabel(run)}
                  </Link>
                  <div className="mt-0.5 text-xs text-zinc-500">
                    Strategy {run.strategy_id.slice(0, 8)}...
                  </div>
                </td>
                <td className="py-3">
                  <RunStatusBadge status={run.status} />
                  {run.error ? <p className="mt-1 max-w-xs break-words text-xs text-red-300">{run.error}</p> : null}
                </td>
                <td className="py-3 text-zinc-300">{String(run.params?.symbol ?? "AAPL")}</td>
                <td className="py-3 text-zinc-300">{String(run.params?.timeframe ?? "1d")}</td>
                <td className="py-3 text-zinc-300">
                  {formatCurrency(Number(run.params?.initial_cash ?? 100000))}
                </td>
                <td className="py-3 text-zinc-400">{formatDateTime(run.completed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MetricComparison({
  runs,
  deltas,
}: {
  runs: ComparedRun[];
  deltas: MetricDelta[];
}) {
  if (deltas.length === 0) {
    return <EmptyPanel title="Metrics" message="No numeric metrics are available for the selected runs." />;
  }

  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">Metrics</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[880px] text-left text-sm">
          <thead className="border-b border-zinc-800 text-zinc-400">
            <tr>
              <th className="pb-3 font-medium">Metric</th>
              {runs.map((run, index) => (
                <th key={run.id} className="pb-3 font-medium">
                  {index === 0 ? "Baseline" : runLabel(run)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {deltas.map((metric) => (
              <tr key={metric.key} className="hover:bg-zinc-900">
                <td className="py-3 text-zinc-100">{metricLabel(metric.key)}</td>
                {runs.map((run, index) => (
                  <td key={run.id} className="py-3">
                    <div className="text-zinc-200">
                      {formatMetricValue(metric.key, metric.values[index])}
                    </div>
                    <div
                      className={`mt-0.5 text-xs ${
                        index === 0
                          ? "text-zinc-500"
                          : (metric.deltas[index] ?? 0) >= 0
                            ? "text-green-400"
                            : "text-red-400"
                      }`}
                    >
                      {formatMetricDelta(metric.key, metric.deltas[index], index === 0)}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EquityOverlay({ overlay }: { overlay: ReturnType<typeof buildEquityOverlay> }) {
  if (overlay.series.length === 0) {
    return (
      <EmptyPanel
        title="Equity Overlay"
        message="No completed selected runs have equity data to chart."
      />
    );
  }

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Equity Overlay</h2>
        <div className="flex flex-wrap gap-3 text-xs text-zinc-400">
          {overlay.series.map((item) => (
            <span key={item.key} className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
              {runLabel(item.run)}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-4 h-80 w-full rounded border border-zinc-800 bg-zinc-900 p-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={overlay.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
            <XAxis
              dataKey="day"
              stroke="#71717a"
              tick={{ fill: "#a1a1aa", fontSize: 12 }}
              label={{ value: "Day", position: "insideBottom", offset: -5, fill: "#a1a1aa" }}
            />
            <YAxis
              stroke="#71717a"
              tick={{ fill: "#a1a1aa", fontSize: 12 }}
              tickFormatter={(value: number) => `$${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#27272a",
                border: "1px solid #3f3f46",
                borderRadius: "6px",
                color: "#f4f4f5",
              }}
              formatter={(value, name) => {
                const item = overlay.series.find((series) => series.key === name);
                return [formatCurrency(value), item ? runLabel(item.run) : String(name)];
              }}
              labelFormatter={(label) => `Day ${label}`}
            />
            {overlay.series.map((item) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                stroke={item.color}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function EmptyPanel({ title, message }: { title?: string; message: string }) {
  return (
    <section className="mt-8">
      {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
      <p className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
        {message}
      </p>
    </section>
  );
}
