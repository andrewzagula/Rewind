"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Strategy } from "@/lib/types";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadStrategies();
  }, []);

  async function loadStrategies() {
    setLoading(true);
    setError("");

    try {
      const res = await apiFetch<{ items: Strategy[]; total: number }>("/api/v1/strategies");
      setStrategies(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load strategies");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Strategies</h1>
        <Link
          href="/strategies/new"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
        >
          New Strategy
        </Link>
      </div>

      {error && (
        <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-8 text-zinc-400">Loading...</p>
      ) : strategies.length === 0 && !error ? (
        <p className="mt-8 text-zinc-400">No strategies yet. Create one to get started.</p>
      ) : strategies.length > 0 ? (
        <table className="mt-8 w-full text-left text-sm">
          <thead className="border-b border-zinc-800 text-zinc-400">
            <tr>
              <th className="pb-3 font-medium">Name</th>
              <th className="pb-3 font-medium">Version</th>
              <th className="pb-3 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {strategies.map((s) => (
              <tr key={s.id} className="hover:bg-zinc-900">
                <td className="py-3">
                  <Link href={`/strategies/${s.id}`} className="text-blue-400 hover:underline">
                    {s.name}
                  </Link>
                </td>
                <td className="py-3 text-zinc-400">v{s.version}</td>
                <td className="py-3 text-zinc-400">
                  {new Date(s.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
