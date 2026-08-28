/**
 * The user's account snapshot — free cash, derived equity, total unrealized P&L, and every
 * open position. Shape is identical to the backend `GET /portfolio` response and the
 * `account_update` WS message (minus `type`). Kept in its own store so a price tick for a
 * pair the user isn't in never touches these subscribers.
 */

import { create } from "zustand";

import type { AccountSnapshot, AccountUpdate } from "@/core/realtime/types";

interface AccountState {
  snapshot: AccountSnapshot | null;
}

export const useAccountStore = create<AccountState>()(() => ({
  snapshot: null,
}));

let pendingSnapshot: AccountSnapshot | null = null;
let frameScheduled = false;

function flush(): void {
  frameScheduled = false;
  if (pendingSnapshot === null) return;
  useAccountStore.setState({ snapshot: pendingSnapshot });
  pendingSnapshot = null;
}

export function applyAccountUpdate(update: AccountUpdate): void {
  const { type: _type, ...snapshot } = update;
  pendingSnapshot = snapshot;
  if (!frameScheduled) {
    frameScheduled = true;
    requestAnimationFrame(flush);
  }
}

export function flushAccountNow(): void {
  flush();
}

/** Drop the snapshot — called on logout so the next session never flashes stale numbers. */
export function resetAccount(): void {
  pendingSnapshot = null;
  useAccountStore.setState({ snapshot: null });
}
