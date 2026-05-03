import { Suspense } from "react";
import ComparePageClient from "./compare-page-client";

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-6xl px-6 py-10 text-sm text-zinc-400">
          Loading comparison...
        </div>
      }
    >
      <ComparePageClient />
    </Suspense>
  );
}
