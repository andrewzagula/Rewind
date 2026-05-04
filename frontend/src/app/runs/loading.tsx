import { SkeletonBlock } from "@/components/progress";

export default function Loading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <SkeletonBlock className="h-8 w-24" />
          <SkeletonBlock className="mt-3 h-4 w-56" />
        </div>
        <div className="flex gap-2">
          <SkeletonBlock className="h-8 w-32" />
          <SkeletonBlock className="h-8 w-20" />
        </div>
      </div>

      <div className="mt-8 overflow-x-auto rounded border border-zinc-800">
        <div className="min-w-[720px]">
          <div className="grid grid-cols-[2.5rem_1fr_7rem_6rem_6rem_7rem] gap-4 border-b border-zinc-800 px-4 py-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-3" />
            ))}
          </div>
          <div className="divide-y divide-zinc-800">
            {Array.from({ length: 6 }).map((_, row) => (
              <div
                key={row}
                className="grid grid-cols-[2.5rem_1fr_7rem_6rem_6rem_7rem] gap-4 px-4 py-4"
              >
                {Array.from({ length: 6 }).map((__, column) => (
                  <SkeletonBlock key={column} className="h-4" />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
