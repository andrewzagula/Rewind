"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { InlineProgress, SkeletonBlock } from "@/components/progress";
import { apiFetch } from "@/lib/api";
import type { Dataset, DatasetFetchRequest, ListResponse } from "@/lib/types";

function formatDate(value: string): string {
  return value ? value.slice(0, 10) : "-";
}

function sourceBadge(source: string): { label: string; className: string } {
  if (!source) return { label: "unknown", className: "border-zinc-700 bg-zinc-900 text-zinc-400" };
  if (source === "synthetic") {
    return { label: "synthetic", className: "border-amber-800 bg-amber-950/30 text-amber-300" };
  }
  return { label: source, className: "border-green-800 bg-green-950/30 text-green-300" };
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [symbol, setSymbol] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [lastFetched, setLastFetched] = useState<Dataset | null>(null);

  const loadDatasets = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<ListResponse<Dataset>>("/api/v1/datasets?limit=100");
      setDatasets(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load datasets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDatasets();
  }, [loadDatasets]);

  async function fetchDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = symbol.trim().toUpperCase();
    if (!trimmed || fetching) return;

    setFetching(true);
    setFetchError("");
    setLastFetched(null);
    const body: DatasetFetchRequest = { symbol: trimmed };
    if (startDate) body.start_date = startDate;
    if (endDate) body.end_date = endDate;

    try {
      const dataset = await apiFetch<Dataset>("/api/v1/datasets/fetch", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setLastFetched(dataset);
      setSymbol("");
      await loadDatasets();
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Failed to fetch market data");
    } finally {
      setFetching(false);
    }
  }

  const realCount = datasets.filter((dataset) => dataset.source && dataset.source !== "synthetic").length;
  const syntheticCount = datasets.filter((dataset) => dataset.source === "synthetic").length;

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Datasets</h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-400">
            Price history the backtester can run against. Real daily bars come from free providers
            with no API key. Datasets marked <span className="text-amber-300">synthetic</span> are
            randomly generated sample files and say nothing about the actual market.
          </p>
        </div>
        <button
          onClick={() => void loadDatasets()}
          className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
        >
          Refresh
        </button>
      </div>

      <section className="mt-8 rounded border border-zinc-800 bg-zinc-900 p-5">
        <h2 className="text-lg font-semibold">Add real market data</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Enter a ticker to download its daily history. Leave the dates blank for the last five
          years. Fetching the same ticker again replaces the earlier file.
        </p>
        <form onSubmit={fetchDataset} className="mt-4 grid gap-4 md:grid-cols-[1fr_1fr_1fr_auto]">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-300">Ticker</span>
            <input
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="NVDA"
              disabled={fetching}
              className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm uppercase text-zinc-100 outline-none focus:border-blue-600 disabled:opacity-60"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-300">Start date</span>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              disabled={fetching}
              className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-blue-600 disabled:opacity-60"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-zinc-300">End date</span>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              disabled={fetching}
              className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-blue-600 disabled:opacity-60"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!symbol.trim() || fetching}
              className="w-full rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 md:w-auto"
            >
              {fetching ? "Fetching..." : "Fetch"}
            </button>
          </div>
        </form>
        {fetching ? (
          <InlineProgress
            label={`Downloading daily bars for ${symbol.trim().toUpperCase()}`}
            detail="This usually takes a few seconds."
            className="mt-4"
          />
        ) : null}
        {fetchError ? (
          <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {fetchError}
          </p>
        ) : null}
        {lastFetched ? (
          <p className="mt-4 rounded border border-green-800 bg-green-950/30 px-3 py-2 text-sm text-green-300">
            Registered {lastFetched.name}: {lastFetched.row_count.toLocaleString()} bars from{" "}
            {formatDate(lastFetched.start_date)} to {formatDate(lastFetched.end_date)} via{" "}
            {lastFetched.source}.
          </p>
        ) : null}
      </section>

      <section className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Registered datasets</h2>
          {!loading ? (
            <p className="text-sm text-zinc-500">
              {realCount} real, {syntheticCount} synthetic
            </p>
          ) : null}
        </div>
        {error ? (
          <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}
        <div className="mt-4 overflow-x-auto rounded border border-zinc-800">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="bg-zinc-900 text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Symbols</th>
                <th className="px-4 py-3">Timeframe</th>
                <th className="px-4 py-3">Range</th>
                <th className="px-4 py-3 text-right">Bars</th>
                <th className="px-4 py-3">Source</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 3 }).map((_, index) => (
                  <tr key={index} className="border-t border-zinc-800">
                    {Array.from({ length: 6 }).map((__, cell) => (
                      <td key={cell} className="px-4 py-3">
                        <SkeletonBlock className="h-3 w-20" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : datasets.length === 0 ? (
                <tr className="border-t border-zinc-800">
                  <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                    No datasets registered yet. Fetch a ticker above to add real market data.
                  </td>
                </tr>
              ) : (
                datasets.map((dataset) => {
                  const badge = sourceBadge(dataset.source);
                  return (
                    <tr key={dataset.id} className="border-t border-zinc-800">
                      <td className="px-4 py-3 font-medium text-zinc-100">{dataset.name}</td>
                      <td className="px-4 py-3 text-zinc-300">{dataset.symbols.join(", ")}</td>
                      <td className="px-4 py-3 text-zinc-300">{dataset.timeframe}</td>
                      <td className="px-4 py-3 text-zinc-300">
                        {formatDate(dataset.start_date)} to {formatDate(dataset.end_date)}
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-300">
                        {dataset.row_count.toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded border px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                          {badge.label}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
