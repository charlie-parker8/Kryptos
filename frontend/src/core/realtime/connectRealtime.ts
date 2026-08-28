/**
 * The single wiring point between a `RealtimeSource` and the stores. Called once from
 * `RealtimeConnector` behind a module guard (`advanced-init-once`) — a component remount
 * must not open a second feed.
 */

import { setBankruptcyEvent } from "@/core/state/bankruptcyStore";
import { applyAccountUpdate } from "@/core/state/accountStore";
import { ingestCandle } from "@/core/state/candleStore";
import { ingestTick } from "@/core/state/marketStore";
import { setPositionEvent } from "@/core/state/positionEventStore";

import type { RealtimeSource } from "./types";

let teardown: (() => void) | null = null;

export function connectRealtime(source: RealtimeSource): () => void {
  if (teardown) return teardown;
  const unsubscribe = source.subscribe((message) => {
    switch (message.type) {
      case "price_tick":
        ingestTick(message);
        break;
      case "candle_update":
        ingestCandle(message);
        break;
      case "account_update":
        applyAccountUpdate(message);
        break;
      case "position_update":
        setPositionEvent(message);
        break;
      case "bankruptcy_reset":
        setBankruptcyEvent(message);
        break;
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
