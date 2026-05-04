import { LoadingPanel, SkeletonBlock, SkeletonText } from "@/components/progress";

export default function Loading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-4">
            <SkeletonBlock className="h-8 w-32" />
            <SkeletonBlock className="h-6 w-20 rounded-full" />
          </div>
          <div className="mt-3 flex flex-wrap gap-3">
            <SkeletonBlock className="h-4 w-36" />
            <SkeletonBlock className="h-4 w-44" />
            <SkeletonBlock className="h-4 w-44" />
          </div>
        </div>
        <div className="flex gap-2">
          <SkeletonBlock className="h-8 w-24" />
          <SkeletonBlock className="h-8 w-24" />
        </div>
      </div>

      <LoadingPanel title="Parameters">
        <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index}>
                <SkeletonBlock className="h-3 w-20" />
                <SkeletonBlock className="mt-2 h-4 w-32" />
              </div>
            ))}
          </div>
          <SkeletonText rows={7} />
        </div>
      </LoadingPanel>

      <LoadingPanel title="Metrics">
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index}>
              <SkeletonBlock className="h-3 w-24" />
              <SkeletonBlock className="mt-2 h-4 w-16" />
            </div>
          ))}
        </div>
      </LoadingPanel>

      <LoadingPanel title="Equity Curve">
        <SkeletonBlock className="h-72 w-full" />
      </LoadingPanel>
    </div>
  );
}
