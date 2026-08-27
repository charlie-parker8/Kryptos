/**
 * Shown next to a price the backend flags `stale` (or older than the 10s max age). Not an
 * error — the last-known value is still displayed; this says "don't trust it to the second".
 */

import { clsx } from "clsx";

import { formatRelative } from "@/core/lib/format";

interface StaleBadgeProps {
  /** the price's as_of timestamp, to show "· 14s ago" */
  since?: string;
  now?: number;
  className?: string;
}

export function StaleBadge({ since, now, className }: StaleBadgeProps) {
  return (
    <span
      className={clsx(
        "k-stale inline-flex items-center gap-1 rounded-control border border-down/40 bg-down/10 px-1.5 py-0.5 text-[0.6875rem] font-medium uppercase tracking-wide text-down",
        className,
      )}
      title="This price is older than the 10-second freshness limit."
    >
      Stale
      {since ? (
        <span className="font-normal opacity-80">
          · {formatRelative(since, now)}
        </span>
      ) : null}
    </span>
  );
}
