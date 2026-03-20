"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { apiFetch } from "@/lib/api";
import type { Run, Trade } from "@/lib/types";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-500/20 text-yellow-400",
  running: "bg-blue-500/20 text-blue-400",
  completed: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
};

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

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [run, setRun] = useState<Run | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchRun();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function fetchRun() {
    apiFetch<Run>(`/api/v1/runs/${id}`).then((r) => {
      setRun(r);
      if (r.status === "pending" || r.status === "running") {
        if (!intervalRef.current) {
          intervalRef.current = setInterval(() => {
            apiFetch<Run>(`/api/v1/runs/${id}`).then((updated) => {
              setRun(updated);
              if (updated.status === "completed" || updated.status === "failed") {
                if (intervalRef.current) clearInterval(intervalRef.current);
                intervalRef.current = null;
                if (updated.status === "completed") loadTrades();
              }
            });
          }, 3000);
        }
      } else if (r.status === "completed") {
        loadTrades();
      }
    });
  }

  function loadTrades() {
    apiFetch<{ items: Trade[]; total: number }>(`/api/v1/runs/${id}/trades`).then(
      (res) => setTrades(res.items)
    );
  }

  if (!run) return <p className="px-6 py-10 text-zinc-400">Loading...</p>;

  const equityCurve = (run.artifacts?.equity_curve as number[]) ?? [];
  const chartData = equityCurve.map((value, i) => ({ day: i + 1, value }));

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      {/* Header */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">Run Detail</h1>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[run.status] ?? ""}`}>
          {run.status}
        </span>
      </div>

      <div className="mt-2 flex gap-4 text-sm text-zinc-400">
        <Link href={`/strategies/${run.strategy_id}`} className="text-blue-400 hover:underline">
          Strategy {run.strategy_id.slice(0, 8)}...
        </Link>
        {run.started_at && <span>Started: {new Date(run.started_at).toLocaleString()}</span>}
        {run.completed_at && <span>Completed: {new Date(run.completed_at).toLocaleString()}</span>}
      </div>

      {run.error && (
        <div className="mt-4 rounded border border-red-800 bg-red-950 p-3 text-sm text-red-300">
          {run.error}
        </div>
      )}

      {/* Metrics */}
      {run.status === "completed" && run.metrics && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold">Metrics</h2>
          <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
            {metricLabels.map(([key, label, fmt]) => {
              const val = (run.metrics as unknown as Record<string, number>)[key];
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
        </div>
      )}

      {/* Equity Curve */}
      {run.status === "completed" && chartData.length > 0 && (
        <div className="mt-8">
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
                  formatter={(value) => [`$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, "Portfolio"]}
                  labelFormatter={(label) => `Day ${label}`}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Trades */}
      {run.status === "completed" && trades.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold">Trades ({trades.length})</h2>
          <table className="mt-4 w-full text-left text-sm">
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
              {trades.map((t) => (
                <tr key={t.id} className="hover:bg-zinc-900">
                  <td className="py-2 text-zinc-100">{t.symbol}</td>
                  <td className={`py-2 ${t.side === "buy" ? "text-green-400" : "text-red-400"}`}>
                    {t.side}
                  </td>
                  <td className="py-2 text-zinc-300">{t.quantity}</td>
                  <td className="py-2 text-zinc-300">${Number(t.price).toFixed(2)}</td>
                  <td className={`py-2 ${Number(t.pnl) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    ${Number(t.pnl).toFixed(2)}
                  </td>
                  <td className="py-2 text-zinc-400">
                    {new Date(t.timestamp).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
