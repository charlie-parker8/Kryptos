/**
 * Deterministic candle data for the no-backend `?mock` / `?frozen` paths. `mockCandleHistory`
 * stands in for `GET /candles`; `mockCandleUpdate` is the forming bar the mock feed pushes.
 * All prices illustrative, not real market data.
 */

import { bucketStartSeconds } from "@/core/lib/candles";

import { IS_FROZEN } from "./mode";
import { gaussian, hashString, mulberry32 } from "./mockRng";
import type { Candle, CandleInterval, CandleUpdate, Pair } from "./types";

const SEED_PRICE: Record<Pair, number> = {
  "BTC/USD": 95204.1,
  "ETH/USD": 3512.9,
  "SOL/USD": 198.44,
};

const HISTORY_BARS = 320;
// Under `?frozen` the mock clock is pinned to the top of the current hour: stable enough
// for a screenshot within a session, still recent so the chart's "stale feed" note stays quiet.
const FROZEN_EPOCH_MS = Math.floor(Date.now() / 3_600_000) * 3_600_000;

export function mockNowMs(): number {
  return IS_FROZEN ? FROZEN_EPOCH_MS : Date.now();
}

export function mockCandleHistory(
  pair: Pair,
  interval: CandleInterval,
  nowMs: number = mockNowMs(),
): Candle[] {
  const rng = mulberry32(hashString(`${pair}:${interval}`));
  const width = interval * 60;
  const current = bucketStartSeconds(Math.floor(nowMs / 1000), interval);
  let price = SEED_PRICE[pair];
  const bars: Candle[] = [];
  for (let i = HISTORY_BARS; i >= 0; i--) {
    const open = price;
    const close = Math.max(open + gaussian(rng) * open * 0.004, open * 0.5);
    const high = Math.max(open, close) * (1 + Math.abs(gaussian(rng)) * 0.0012);
    const low = Math.min(open, close) * (1 - Math.abs(gaussian(rng)) * 0.0012);
    bars.push({
      open_time: current - i * width,
      open: open.toFixed(2),
      high: high.toFixed(2),
      low: low.toFixed(2),
      close: close.toFixed(2),
      volume: (Math.abs(gaussian(rng)) * 8).toFixed(4),
    });
    price = close;
  }
  return bars;
}

export function mockCandleUpdate(
  pair: Pair,
  interval: CandleInterval,
  price: number,
  nowMs: number = mockNowMs(),
  closed = false,
): CandleUpdate {
  const spread = price * 0.0015;
  return {
    type: "candle_update",
    pair,
    interval,
    open_time: bucketStartSeconds(Math.floor(nowMs / 1000), interval),
    open: (price - spread).toFixed(2),
    high: (price + spread).toFixed(2),
    low: (price - spread * 1.5).toFixed(2),
    close: price.toFixed(2),
    volume: "1.0000",
    closed,
    broadcast_at: nowMs,
  };
}
