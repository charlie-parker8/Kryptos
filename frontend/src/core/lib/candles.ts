/** Framework-free candle helpers — bucket alignment and history/overlay merge. */

import type { Candle } from "@/core/realtime/types";

/** Start (unix seconds) of the `intervalMinutes`-wide bucket that contains `unixSeconds`. */
export function bucketStartSeconds(
  unixSeconds: number,
  intervalMinutes: number,
): number {
  const width = intervalMinutes * 60;
  return Math.floor(unixSeconds / width) * width;
}

/**
 * Merge the REST history seed with the live WS overlay: a bar from `live` wins over a
 * `seed` bar with the same `open_time`, later `live` bars are appended, and the result is
 * ascending and de-duplicated. History stays authoritative for anything older than the
 * overlap; the periodic `useCandles` refetch reconciles the rest.
 */
export function mergeCandles(
  seed: readonly Candle[],
  live: readonly Candle[],
): Candle[] {
  const byTime = new Map<number, Candle>();
  for (const bar of seed) byTime.set(bar.open_time, bar);
  for (const bar of live) byTime.set(bar.open_time, bar);
  return [...byTime.values()].sort((a, b) => a.open_time - b.open_time);
}
