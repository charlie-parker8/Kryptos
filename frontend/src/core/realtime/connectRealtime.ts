/**
 * The single wiring point between a `RealtimeSource` and the two stores. Called once from
 * `main.tsx` behind a module guard (`advanced-init-once`) — a component remount must not
 * open a second feed.
 */

import { setBankruptcyEvent } from "@/core/state/bankruptcyStore";
import { ingestCandle } from "@/core/state/candleStore";
import { applyPortfolioUpdate } from "@/core/state/portfolioStore";
import { ingestTick } from "@/core/state/marketStore";

import type { RealtimeSource } from "./types";

let teardown: (() => void) | null = null;

export function connectRealtime(source: RealtimeSource): () => void {
  if (teardown) return teardown;
  const unsubscribe = source.subscribe((message) => {
    if (message.type === "price_tick") {
      ingestTick(message);
    } else if (message.type === "candle_update") {
      ingestCandle(message);
    } else if (message.type === "bankruptcy_reset") {
      setBankruptcyEvent(message);
    } else {
      applyPortfolioUpdate(message);
    }
  });
  teardown = () => {
    unsubscribe();
    teardown = null;
  };
  return teardown;
}

/** Tear down the active feed, if any — called on logout so a new session starts clean. */
export function disconnectRealtime(): void {
  teardown?.();
}
