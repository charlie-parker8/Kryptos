/**
 * The user's portfolio snapshot — cash, holdings, net worth. Shape is identical to the
 * backend `GET /portfolio` response and the `portfolio_update` WS message (minus `type`).
 * Kept in its own store so a price tick for an unheld pair never touches these
 * subscribers, and an order fill never re-renders the price cells
 * (`rerender-split-combined-hooks`).
 */

import { create } from "zustand";

import type { PortfolioSnapshot, PortfolioUpdate } from "@/core/realtime/types";

interface PortfolioState {
  snapshot: PortfolioSnapshot | null;
}

export const usePortfolioStore = create<PortfolioState>()(() => ({
  snapshot: null,
}));

let pendingSnapshot: PortfolioSnapshot | null = null;
let frameScheduled = false;

function flush(): void {
  frameScheduled = false;
  if (pendingSnapshot === null) return;
  usePortfolioStore.setState({ snapshot: pendingSnapshot });
  pendingSnapshot = null;
}

export function applyPortfolioUpdate(update: PortfolioUpdate): void {
  const { type: _type, ...snapshot } = update;
  pendingSnapshot = snapshot;
  if (!frameScheduled) {
    frameScheduled = true;
    requestAnimationFrame(flush);
  }
}

export function flushPortfolioNow(): void {
  flush();
}

/** Drop the snapshot — called on logout so the next session never flashes stale numbers. */
export function resetPortfolio(): void {
  pendingSnapshot = null;
  usePortfolioStore.setState({ snapshot: null });
}
