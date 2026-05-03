import type { Run } from "@/lib/types";

const statusStyles: Record<Run["status"], string> = {
  pending: "border-yellow-500/30 bg-yellow-500/15 text-yellow-300",
  running: "border-blue-500/30 bg-blue-500/15 text-blue-300",
  completed: "border-green-500/30 bg-green-500/15 text-green-300",
  failed: "border-red-500/30 bg-red-500/15 text-red-300",
};

export default function RunStatusBadge({
  status,
  className = "",
}: {
  status: Run["status"] | string;
  className?: string;
}) {
  const knownStatus = status as Run["status"];
  const style = Object.prototype.hasOwnProperty.call(statusStyles, status)
    ? statusStyles[knownStatus]
    : "border-zinc-600 bg-zinc-800 text-zinc-300";

  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${style} ${className}`}
    >
      {status}
    </span>
  );
}
