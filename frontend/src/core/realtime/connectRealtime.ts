/**
 * The single wiring point between a `RealtimeSource` and the two stores. Called once from
 * `main.tsx` behind a module guard (`advanced-init-once`) — a component remount must not
 * open a second feed.
 */

import { applyPortfolioUpdate } from "@/core/state/portfolioStore";
import { ingestTick } from "@/core/state/marketStore";

import type { RealtimeSource } from "./types";

let teardown: (() => void) | null = null;

export function connectRealtime(source: RealtimeSource): () => void {
  if (teardown) return teardown;
  const unsubscribe = source.subscribe((message) => {
    if (message.type === "price_tick") {
      ingestTick(message);
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
