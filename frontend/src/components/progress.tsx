import type { ReactNode } from "react";

export function LoadingSpinner({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
    />
  );
}

export function InlineProgress({
  label,
  detail,
  className = "",
}: {
  label: string;
  detail?: string;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2 text-sm text-zinc-300 ${className}`}>
      <LoadingSpinner className="text-blue-300" />
      <span>{label}</span>
      {detail ? <span className="text-zinc-500">{detail}</span> : null}
    </span>
  );
}

export function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-zinc-800/80 ${className}`} />;
}

export function SkeletonText({
  rows = 3,
  className = "",
}: {
  rows?: number;
  className?: string;
}) {
  const widths = ["w-11/12", "w-8/12", "w-10/12", "w-7/12"];

  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, index) => (
        <SkeletonBlock key={index} className={`h-3 ${widths[index % widths.length]}`} />
      ))}
    </div>
  );
}

export function LoadingPanel({
  title,
  children,
  className = "",
}: {
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`mt-8 ${className}`}>
      {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
      <div className="mt-4 rounded border border-zinc-800 bg-zinc-900 p-4">
        {children ?? <SkeletonText />}
      </div>
    </section>
  );
}
