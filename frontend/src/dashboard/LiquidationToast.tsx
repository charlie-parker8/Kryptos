/**
 * A transient notice when a position is force-closed by the liquidation engine
 * (`position_update` with `status: "liquidated"`). The user didn't ask for it, so they get
 * told — but it's a toast, not a modal (that's reserved for a full account wipeout).
 * Auto-dismisses after a few seconds; mounted once in the shell.
 */

import { useEffect } from "react";

import { formatSignedUsd, formatUsd } from "@/core/lib/money";
import {
  dismissPositionEvent,
  usePositionEventStore,
} from "@/core/state/positionEventStore";

export function LiquidationToast() {
  const event = usePositionEventStore((s) => s.event);
  const isLiquidation = event?.status === "liquidated";

  useEffect(() => {
    if (!isLiquidation) return;
    const timer = setTimeout(dismissPositionEvent, 8000);
    return () => clearTimeout(timer);
  }, [isLiquidation, event?.position_id]);

  if (!event || !isLiquidation) return null;

  const pnl = Number(event.realized_pnl);

  return (
    <div
      role="alert"
      className="fixed bottom-16 left-1/2 z-50 -translate-x-1/2 border border-down/50 bg-surface px-4 py-3 font-mono text-xs shadow-lg"
    >
      <p className="font-semibold uppercase tracking-wide text-down">
        {event.pair} {event.side} liquidated
      </p>
      <p className="mt-1 text-muted">
        Closed at {formatUsd(event.close_price)} ·{" "}
        <span className={pnl < 0 ? "text-down" : "text-up"}>
          {formatSignedUsd(pnl)}
        </span>
      </p>
      <button
        type="button"
        onClick={dismissPositionEvent}
        className="mt-2 text-[0.6875rem] uppercase tracking-wide text-muted hover:text-fg"
      >
        Dismiss
      </button>
    </div>
  );
}
