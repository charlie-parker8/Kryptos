/** Mirrors the backend `KRYPTOS_PRICE_MAX_AGE_SECONDS` (default 10s) that drives `stale`. */
export const PRICE_MAX_AGE_MS = 10_000;

export function isStale(asOf: string, now: number = Date.now()): boolean {
  const t = Date.parse(asOf);
  if (Number.isNaN(t)) return true;
  return now - t > PRICE_MAX_AGE_MS;
}
