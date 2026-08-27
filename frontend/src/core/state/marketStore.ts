/**
 * Latest price per pair. Ticks arrive several times a second; they are buffered in a
 * module-level map (outside React — `rerender-use-ref-transient-values`) and flushed to
 * the store at most once per animation frame, so a burst becomes one render. Components
 * subscribe to narrow slices (`s => s.ticks[pair]?.last`) so a BTC tick never re-renders
 * an ETH cell.
 */

import { create } from "zustand";

import type { Pair, PriceTick } from "@/core/realtime/types";

interface MarketState {
  ticks: Partial<Record<Pair, PriceTick>>;
}

export const useMarketStore = create<MarketState>()(() => ({ ticks: {} }));

const pending = new Map<Pair, PriceTick>();
let frameScheduled = false;

function flush(): void {
  frameScheduled = false;
  if (pending.size === 0) return;
  const next = { ...useMarketStore.getState().ticks };
  for (const [pair, tick] of pending) next[pair] = tick;
  pending.clear();
  useMarketStore.setState({ ticks: next });
}

export function ingestTick(tick: PriceTick): void {
  pending.set(tick.pair, tick);
  if (!frameScheduled) {
    frameScheduled = true;
    requestAnimationFrame(flush);
  }
}

/** Test/prototype helper — force a synchronous flush (used by frozen mock mode). */
export function flushTicksNow(): void {
  flush();
}
