"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { InlineProgress, LoadingPanel, SkeletonBlock } from "@/components/progress";
import RunStatusBadge from "@/components/run-status-badge";
import { apiFetch } from "@/lib/api";
import type { Dataset, Run, Trade } from "@/lib/types";

const TRADE_PAGE_SIZE = 25;
const RUN_POLL_INTERVAL_MS = 3000;

const metricLabels: [string, string, (v: number) => string][] = [
  ["total_return", "Total Return", (v) => `${(v * 100).toFixed(2)}%`],
  ["annualized_return", "Annualized Return", (v) => `${(v * 100).toFixed(2)}%`],
  ["sharpe_ratio", "Sharpe Ratio", (v) => v.toFixed(3)],
  ["sortino_ratio", "Sortino Ratio", (v) => v.toFixed(3)],
  ["max_drawdown", "Max Drawdown", (v) => `${(v * 100).toFixed(2)}%`],
  ["calmar_ratio", "Calmar Ratio", (v) => v.toFixed(3)],
  ["volatility_annual", "Annual Volatility", (v) => `${(v * 100).toFixed(2)}%`],
  ["total_trades", "Total Trades", (v) => v.toString()],
  ["win_rate", "Win Rate", (v) => `${(v * 100).toFixed(1)}%`],
  ["profit_factor", "Profit Factor", (v) => v.toFixed(2)],
  ["avg_trade_pnl", "Avg Trade PnL", (v) => `$${v.toFixed(2)}`],
  ["avg_win", "Avg Win", (v) => `$${v.toFixed(2)}`],
  ["avg_loss", "Avg Loss", (v) => `$${v.toFixed(2)}`],
];

const tradeSortOptions = [
  { value: "timestamp", label: "Time" },
  { value: "symbol", label: "Symbol" },
  { value: "side", label: "Side" },
  { value: "quantity", label: "Qty" },
  { value: "price", label: "Price" },
  { value: "pnl", label: "PnL" },
];

type EquityPoint = {
  index: number;
  timestamp: string;
  value: number;
};

type ChartPoint = EquityPoint & {
  day: number;
  drawdown: number;
};

type TradeMarker = {
  id: string;
  day: number;
  value: number;
  side: Trade["side"];
};

function toDateKey(value: unknown): string {
  if (!value) return "";
  const parsed = new Date(String(value));
  if (!Number.isNaN(parsed.getTime())) return parsed.toISOString().slice(0, 10);
  return String(value).slice(0, 10);
}

function formatCurrency(value: unknown): string {
  return `$${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleDateString() : "-";
}

function chatRunPath(runId: string, prompt: string): string {
  const query = new URLSearchParams({
    context: "run",
    run_id: runId,
    prompt,
  });
  return `/chat?${query.toString()}`;
}

function isActiveRun(run: Run): boolean {
  return run.status === "pending" || run.status === "running";
}

function formatRefreshTime(value: Date | null): string {
  return value ? value.toLocaleTimeString() : "waiting for first refresh";
}

function getEquityPoints(run: Run): EquityPoint[] {
  const rawPoints = run.artifacts?.equity_points;
  if (Array.isArray(rawPoints)) {
    return rawPoints
      .map((point, fallbackIndex) => {
        const record = point as Record<string, unknown>;
        return {
          index: Number(record.index ?? fallbackIndex),
          timestamp: String(record.timestamp ?? ""),
          value: Number(record.value),
        };
      })
      .filter((point) => Number.isFinite(point.value));
  }

  const rawCurve = run.artifacts?.equity_curve;
  if (!Array.isArray(rawCurve)) return [];
  return rawCurve
    .map((value, index) => ({
      index,
      timestamp: "",
      value: Number(value),
    }))
    .filter((point) => Number.isFinite(point.value));
}

function getChartData(points: EquityPoint[]): ChartPoint[] {
  let peak = 0;
  return points.map((point) => {
    peak = Math.max(peak, point.value);
    const drawdown = peak > 0 ? (point.value - peak) / peak : 0;
    return {
      ...point,
      day: point.index + 1,
      drawdown,
    };
  });
}

function getTradeMarkers(chartData: ChartPoint[], trades: Trade[]): TradeMarker[] {
  const pointsByDate = new Map(
    chartData
      .map((point) => [toDateKey(point.timestamp), point] as const)
      .filter(([date]) => date)
  );

  return trades
    .map((trade) => {
      const point = pointsByDate.get(toDateKey(trade.timestamp));
      if (!point) return null;
      return {
        id: trade.id,
        day: point.day,
        value: point.value,
        side: trade.side,
      };
    })
    .filter((marker): marker is TradeMarker => marker !== null);
}

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [run, setRun] = useState<Run | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [tradeTotal, setTradeTotal] = useState(0);
  const [tradePage, setTradePage] = useState(0);
  const [tradeSortBy, setTradeSortBy] = useState("timestamp");
  const [tradeSortDir, setTradeSortDir] = useState<"asc" | "desc">("asc");
  const [tradesLoading, setTradesLoading] = useState(false);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [datasetError, setDatasetError] = useState("");
  const [isPolling, setIsPolling] = useState(false);
  const [lastRunRefreshAt, setLastRunRefreshAt] = useState<Date | null>(null);
  const [error, setError] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTrades = useCallback(
    async (page: number, sortBy: string, sortDir: "asc" | "desc") => {
      setTradesLoading(true);
      try {
        const query = new URLSearchParams({
          limit: String(TRADE_PAGE_SIZE),
          offset: String(page * TRADE_PAGE_SIZE),
          sort_by: sortBy,
          sort_dir: sortDir,
        });
        const res = await apiFetch<{ items: Trade[]; total: number }>(
          `/api/v1/runs/${id}/trades?${query.toString()}`
        );
        setTrades(res.items);
        setTradeTotal(res.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load trades");
      } finally {
        setTradesLoading(false);
      }
    },
    [id]
  );

  useEffect(() => {
    async function pollRun() {
      try {
        const updated = await apiFetch<Run>(`/api/v1/runs/${id}`);
        setRun(updated);
        setLastRunRefreshAt(new Date());

        if (updated.status === "completed" || updated.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          intervalRef.current = null;
          setIsPolling(false);
        } else {
          setIsPolling(true);
        }
      } catch (err) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        intervalRef.current = null;
        setIsPolling(false);
        setError(err instanceof Error ? err.message : "Failed to refresh run");
      }
    }

    async function fetchRun() {
      setError("");
      setRun(null);
      setDataset(null);
      setDatasetError("");
      setTrades([]);
      setTradeTotal(0);
      setTradePage(0);
      setIsPolling(false);
      setLastRunRefreshAt(null);

      try {
        const currentRun = await apiFetch<Run>(`/api/v1/runs/${id}`);
        setRun(currentRun);
        setLastRunRefreshAt(new Date());

        if (isActiveRun(currentRun)) {
          setIsPolling(true);
          intervalRef.current = setInterval(() => {
            void pollRun();
          }, RUN_POLL_INTERVAL_MS);
        }
      } catch (err) {
        setIsPolling(false);
        setError(err instanceof Error ? err.message : "Failed to load run");
      }
    }

    void fetchRun();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
    };
  }, [id]);

  useEffect(() => {
    async function fetchDataset(datasetId: string) {
      setDatasetError("");
      try {
        const currentDataset = await apiFetch<Dataset>(`/api/v1/datasets/${datasetId}`);
        setDataset(currentDataset);
      } catch (err) {
        setDataset(null);
        setDatasetError(err instanceof Error ? err.message : "Failed to load dataset");
      }
    }

    if (!run?.dataset_id) {
      setDataset(null);
      setDatasetError("");
      return;
    }

    void fetchDataset(run.dataset_id);
  }, [run?.dataset_id]);

  useEffect(() => {
    if (run?.status === "completed") {
      void loadTrades(tradePage, tradeSortBy, tradeSortDir);
    }
  }, [loadTrades, run?.status, tradePage, tradeSortBy, tradeSortDir]);

  if (!run) {
    return (
      <div className="mx-auto w-full max-w-6xl px-6 py-10">
        {error ? (
          <p className="rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : (
          <LoadingPanel>
            <InlineProgress label="Loading run detail..." />
          </LoadingPanel>
        )}
      </div>
    );
  }

  const chartData = getChartData(getEquityPoints(run));
  const tradeMarkers = getTradeMarkers(chartData, trades);
  const metrics = run.metrics as unknown as Record<string, number>;
  const hasMetrics = run.status === "completed" && Object.keys(run.metrics ?? {}).length > 0;
  const totalTradePages = Math.max(1, Math.ceil(tradeTotal / TRADE_PAGE_SIZE));
  const activeRun = isActiveRun(run);

  function updateTradeSort(sortBy: string) {
    if (sortBy === tradeSortBy) {
      setTradeSortDir((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setTradeSortBy(sortBy);
      setTradeSortDir("asc");
    }
    setTradePage(0);
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-4">
            <h1 className="text-2xl font-bold">Run Detail</h1>
            <RunStatusBadge status={run.status} className="px-2.5" />
          </div>

          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-zinc-400">
            <Link href={`/strategies/${run.strategy_id}`} className="text-blue-400 hover:underline">
              Strategy {run.strategy_id.slice(0, 8)}...
            </Link>
            {run.started_at && <span>Started: {new Date(run.started_at).toLocaleString()}</span>}
            {run.completed_at && <span>Completed: {new Date(run.completed_at).toLocaleString()}</span>}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            href={chatRunPath(run.id, "Analyze this run and explain the most important results.")}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Ask Rewind
          </Link>
          <Link
            href={chatRunPath(run.id, "Why did this run lose money?")}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
          >
            Explain loss
          </Link>
        </div>
      </div>

      {run.status === "failed" && (
        <div className="mt-6 rounded border border-red-800 bg-red-950 p-4 text-sm text-red-200">
          <p className="font-medium">Run failed</p>
          <p className="mt-2 break-words text-red-300">{run.error || "No error details were stored."}</p>
        </div>
      )}

      {activeRun && (
        <RunProgressPanel
          run={run}
          isPolling={isPolling}
          lastRunRefreshAt={lastRunRefreshAt}
        />
      )}

      {error && (
        <div className="mt-4 rounded border border-red-800 bg-red-950 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Parameters</h2>
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.2fr]">
          <div className="grid gap-3 rounded border border-zinc-800 bg-zinc-900 p-4 sm:grid-cols-2">
            <Fact label="Symbol" value={String(run.params?.symbol ?? "AAPL")} />
            <Fact label="Timeframe" value={String(run.params?.timeframe ?? "1d")} />
            <Fact label="Initial Cash" value={formatCurrency(run.params?.initial_cash ?? 100000)} />
            <Fact label="Status" value={run.status} />
            <Fact label="Strategy ID" value={run.strategy_id} wide />
            {run.dataset_id ? (
              <>
                <Fact
                  label="Dataset"
                  value={dataset?.name ?? (datasetError || "Loading dataset...")}
                  wide
                />
                {dataset ? (
                  <>
                    <Fact label="Dataset Symbols" value={dataset.symbols.join(", ")} />
                    <Fact label="Dataset Timeframe" value={dataset.timeframe} />
                    <Fact
                      label="Dataset Dates"
                      value={`${formatDate(dataset.start_date)} - ${formatDate(dataset.end_date)}`}
                      wide
                    />
                    <Fact label="Dataset Rows" value={dataset.row_count.toLocaleString()} />
                    <Fact
                      label="Dataset Version"
                      value={(run.dataset_version || dataset.checksum).slice(0, 12)}
                    />
                    <Fact label="Dataset File" value={dataset.file_path} wide />
                  </>
                ) : null}
              </>
            ) : (
              <Fact label="Dataset" value="Legacy sample fallback" wide />
            )}
            {run.error ? <Fact label="Error" value={run.error} wide /> : null}
          </div>
          <pre className="min-h-40 overflow-x-auto rounded border border-zinc-800 bg-zinc-950 p-4 text-xs text-zinc-300">
            {JSON.stringify(run.params ?? {}, null, 2)}
          </pre>
        </div>
      </section>

      {hasMetrics ? (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">Metrics</h2>
          <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
            {metricLabels.map(([key, label, fmt]) => {
              const val = metrics[key];
              return (
                <div key={key}>
                  <p className="text-xs text-zinc-400">{label}</p>
                  <p className="text-sm font-medium text-zinc-100">
                    {val != null ? fmt(val) : "-"}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      ) : activeRun ? (
        <PendingMetricsPanel />
      ) : null}

      {run.status === "completed" && chartData.length > 0 ? (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">Equity Curve</h2>
          <div className="mt-4 h-80 w-full rounded border border-zinc-800 bg-zinc-900 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
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
                  tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#27272a",
                    border: "1px solid #3f3f46",
                    borderRadius: "6px",
                    color: "#f4f4f5",
                  }}
                  formatter={(value) => [formatCurrency(value), "Portfolio"]}
                  labelFormatter={(label) => `Day ${label}`}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                />
                {tradeMarkers.map((marker) => (
                  <ReferenceDot
                    key={marker.id}
                    x={marker.day}
                    y={marker.value}
                    r={4}
                    fill={marker.side === "buy" ? "#22c55e" : "#ef4444"}
                    stroke="#18181b"
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      ) : run.status === "completed" ? (
        <EmptyPanel title="Equity Curve" message="No equity curve artifact was stored for this run." />
      ) : activeRun ? (
        <PendingChartPanel
          title="Equity Curve"
          message="Equity data will appear after the worker stores run artifacts."
        />
      ) : null}

      {run.status === "completed" && chartData.length > 0 && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">Drawdown</h2>
          <div className="mt-4 h-64 w-full rounded border border-zinc-800 bg-zinc-900 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
                <XAxis dataKey="day" stroke="#71717a" tick={{ fill: "#a1a1aa", fontSize: 12 }} />
                <YAxis
                  stroke="#71717a"
                  tick={{ fill: "#a1a1aa", fontSize: 12 }}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#27272a",
                    border: "1px solid #3f3f46",
                    borderRadius: "6px",
                    color: "#f4f4f5",
                  }}
                  formatter={(value) => [`${(Number(value) * 100).toFixed(2)}%`, "Drawdown"]}
                  labelFormatter={(label) => `Day ${label}`}
                />
                <Area type="monotone" dataKey="drawdown" stroke="#f97316" fill="#f97316" fillOpacity={0.25} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {activeRun ? (
        <PendingChartPanel
          title="Drawdown"
          message="Drawdown will be calculated from the completed equity curve."
          compact
        />
      ) : null}

      {run.status === "completed" ? (
        <section className="mt-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Trades ({tradeTotal})</h2>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-zinc-400">Sort</span>
              {tradeSortOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => updateTradeSort(option.value)}
                  className={`rounded border px-2 py-1 ${
                    tradeSortBy === option.value
                      ? "border-blue-500 text-blue-300"
                      : "border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  }`}
                >
                  {option.label}
                  {tradeSortBy === option.value ? ` ${tradeSortDir === "asc" ? "up" : "down"}` : ""}
                </button>
              ))}
            </div>
          </div>

          {tradesLoading ? (
            <p className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
              Loading trades...
            </p>
          ) : trades.length === 0 ? (
            <p className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
              No trades were generated by this run.
            </p>
          ) : (
            <>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead className="border-b border-zinc-800 text-zinc-400">
                    <tr>
                      <th className="pb-3 font-medium">Symbol</th>
                      <th className="pb-3 font-medium">Side</th>
                      <th className="pb-3 font-medium">Qty</th>
                      <th className="pb-3 font-medium">Price</th>
                      <th className="pb-3 font-medium">PnL</th>
                      <th className="pb-3 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {trades.map((trade) => (
                      <tr key={trade.id} className="hover:bg-zinc-900">
                        <td className="py-2 text-zinc-100">{trade.symbol}</td>
                        <td className={`py-2 ${trade.side === "buy" ? "text-green-400" : "text-red-400"}`}>
                          {trade.side}
                        </td>
                        <td className="py-2 text-zinc-300">{Number(trade.quantity).toLocaleString()}</td>
                        <td className="py-2 text-zinc-300">{formatCurrency(trade.price)}</td>
                        <td className={`py-2 ${Number(trade.pnl) >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {formatCurrency(trade.pnl)}
                        </td>
                        <td className="py-2 text-zinc-400">
                          {new Date(trade.timestamp).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 flex items-center justify-between text-sm">
                <button
                  onClick={() => setTradePage((page) => Math.max(0, page - 1))}
                  disabled={tradePage === 0}
                  className="rounded border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-zinc-400">
                  Page {tradePage + 1} of {totalTradePages}
                </span>
                <button
                  onClick={() => setTradePage((page) => Math.min(totalTradePages - 1, page + 1))}
                  disabled={tradePage + 1 >= totalTradePages}
                  className="rounded border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </>
          )}
        </section>
      ) : activeRun ? (
        <PendingTradesPanel />
      ) : null}
    </div>
  );
}

function Fact({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : ""}>
      <p className="text-xs text-zinc-400">{label}</p>
      <p className="mt-1 break-words text-sm font-medium text-zinc-100">{value}</p>
    </div>
  );
}

function EmptyPanel({ title, message }: { title: string; message: string }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
        {message}
      </p>
    </section>
  );
}

function RunProgressPanel({
  run,
  isPolling,
  lastRunRefreshAt,
}: {
  run: Run;
  isPolling: boolean;
  lastRunRefreshAt: Date | null;
}) {
  const statusDetail =
    run.status === "pending"
      ? "Queued for the worker. No metrics have been written yet."
      : "Worker is executing the strategy and will write metrics, trades, and artifacts when complete.";

  return (
    <div className="mt-6 rounded border border-blue-900/70 bg-blue-950/20 p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium text-blue-200">Run in progress</p>
          <p className="mt-1 text-zinc-300">{statusDetail}</p>
        </div>
        <RunStatusBadge status={run.status} />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-zinc-400">
        {isPolling ? (
          <InlineProgress
            label={`Checking every ${RUN_POLL_INTERVAL_MS / 1000}s`}
            className="text-xs"
          />
        ) : (
          <span>Polling paused</span>
        )}
        <span>Last checked: {formatRefreshTime(lastRunRefreshAt)}</span>
        <span>Created: {new Date(run.created_at).toLocaleString()}</span>
        {run.started_at ? <span>Started: {new Date(run.started_at).toLocaleString()}</span> : null}
      </div>
    </div>
  );
}

function PendingMetricsPanel() {
  return (
    <LoadingPanel title="Metrics">
      <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
        {metricLabels.slice(0, 8).map(([key, label]) => (
          <div key={key}>
            <p className="text-xs text-zinc-500">{label}</p>
            <SkeletonBlock className="mt-2 h-4 w-16" />
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-zinc-500">Metrics will appear when the run completes.</p>
    </LoadingPanel>
  );
}

function PendingChartPanel({
  title,
  message,
  compact = false,
}: {
  title: string;
  message: string;
  compact?: boolean;
}) {
  return (
    <LoadingPanel title={title}>
      <SkeletonBlock className={`${compact ? "h-52" : "h-72"} w-full`} />
      <p className="mt-4 text-sm text-zinc-500">{message}</p>
    </LoadingPanel>
  );
}

function PendingTradesPanel() {
  return (
    <LoadingPanel title="Trades">
      <div className="space-y-3">
        <div className="grid grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-3" />
          ))}
        </div>
        {Array.from({ length: 4 }).map((_, row) => (
          <div key={row} className="grid grid-cols-6 gap-3">
            {Array.from({ length: 6 }).map((__, column) => (
              <SkeletonBlock key={column} className="h-4" />
            ))}
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-zinc-500">
        Trades will load after the completed run is available.
      </p>
    </LoadingPanel>
  );
}
