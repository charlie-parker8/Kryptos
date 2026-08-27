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
  /**
   * First `last` price observed per pair this session — the reference the ladder/tape
   * "since open" change is measured against. There is no backend 24h-history feed, so this
   * is the honest available anchor: how the price has moved since the user opened the app.
   */
  anchors: Partial<Record<Pair, string>>;
}

export const useMarketStore = create<MarketState>()(() => ({
  ticks: {},
  anchors: {},
}));

const pending = new Map<Pair, PriceTick>();
let frameScheduled = false;

function flush(): void {
  frameScheduled = false;
  if (pending.size === 0) return;
  const state = useMarketStore.getState();
  const next = { ...state.ticks };
  const nextAnchors = { ...state.anchors };
  for (const [pair, tick] of pending) {
    next[pair] = tick;
    nextAnchors[pair] ??= tick.last;
  }
  pending.clear();
  useMarketStore.setState({ ticks: next, anchors: nextAnchors });
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

/** Clear ticks + session anchors — called on logout so the next session starts fresh. */
export function resetMarket(): void {
  pending.clear();
  useMarketStore.setState({ ticks: {}, anchors: {} });
}
