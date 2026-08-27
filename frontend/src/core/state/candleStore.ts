/**
 * Live candle bars (the forming bar plus any just-closed one) per (pair, interval), pushed
 * over `/ws` as `candle_update`. Like `marketStore`, frames are buffered outside React and
 * flushed at most once per animation frame, so a burst becomes one render. The chart merges
 * this overlay onto the REST history from `useCandles` — that history stays authoritative
 * for anything older than what's here.
 */

import { create } from "zustand";

import type {
  Candle,
  CandleInterval,
  CandleUpdate,
  Pair,
} from "@/core/realtime/types";

export type CandleKey = `${Pair}:${CandleInterval}`;

/** Live bars retained per key — minutes of updates; the REST seed carries real history. */
const MAX_BARS_PER_KEY = 800;

interface CandleState {
  /** keyed by `pair:interval`, then by bar open_time (unix seconds). */
  live: Partial<Record<CandleKey, Record<number, Candle>>>;
}

export const useCandleStore = create<CandleState>()(() => ({ live: {} }));

export function candleKey(pair: Pair, interval: CandleInterval): CandleKey {
  return `${pair}:${interval}`;
}

const pending = new Map<CandleKey, CandleUpdate[]>();
let frameScheduled = false;

function toCandle(update: CandleUpdate): Candle {
  return {
    open_time: update.open_time,
    open: update.open,
    high: update.high,
    low: update.low,
    close: update.close,
    volume: update.volume,
  };
}

function flush(): void {
  frameScheduled = false;
  if (pending.size === 0) return;
  const live = { ...useCandleStore.getState().live };
  for (const [key, updates] of pending) {
    const bars: Record<number, Candle> = { ...live[key] };
    for (const update of updates) bars[update.open_time] = toCandle(update);
    const times = Object.keys(bars)
      .map(Number)
      .sort((a, b) => a - b);
    for (const stale of times.slice(0, Math.max(0, times.length - MAX_BARS_PER_KEY))) {
      delete bars[stale];
    }
    live[key] = bars;
  }
  pending.clear();
  useCandleStore.setState({ live });
}

export function ingestCandle(update: CandleUpdate): void {
  const key = candleKey(update.pair, update.interval);
  const queued = pending.get(key);
  if (queued) queued.push(update);
  else pending.set(key, [update]);
  if (!frameScheduled) {
    frameScheduled = true;
    requestAnimationFrame(flush);
  }
}

/** Test/prototype helper — force a synchronous flush (used by frozen mock mode). */
export function flushCandlesNow(): void {
  flush();
}

/** Clear on logout so the next session starts fresh. */
export function resetCandles(): void {
  pending.clear();
  useCandleStore.setState({ live: {} });
}
