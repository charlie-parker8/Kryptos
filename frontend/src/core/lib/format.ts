/** Presentation constants + non-money formatting (time, labels). Money lives in `money.ts`. */

import type { Asset, Pair } from "@/core/realtime/types";

/** Display precision per pair — how many fraction digits we show for a quantity. */
export const PAIR_PRECISION: Record<Pair, number> = {
  "BTC/USD": 8,
  "ETH/USD": 6,
  "SOL/USD": 4,
};

export const ASSET_OF: Record<Pair, Asset> = {
  "BTC/USD": "BTC",
  "ETH/USD": "ETH",
  "SOL/USD": "SOL",
};

export const PAIR_OF: Record<Asset, Pair> = {
  BTC: "BTC/USD",
  ETH: "ETH/USD",
  SOL: "SOL/USD",
};

export const ASSET_NAME: Record<Asset, string> = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  SOL: "Solana",
};

/** "just now" / "3s ago" / "1m ago" — drives the stale-price affordance. */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 2) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}

/** Clock time for the "updated" line, e.g. "14:03:21". */
export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-US", { hour12: false });
}
