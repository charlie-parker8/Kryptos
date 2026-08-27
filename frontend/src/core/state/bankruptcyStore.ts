/**
 * The most recent bankruptcy-reset event, if the user hasn't dismissed it. Its own store so
 * the modal is the only thing that re-renders when a reset lands. A `bankruptcy_reset` WS
 * message is a rare, deliberate moment — not a stream — so no rAF coalescing here.
 */

import { create } from "zustand";

import type { BankruptcyReset } from "@/core/realtime/types";

interface BankruptcyState {
  event: BankruptcyReset | null;
}

export const useBankruptcyStore = create<BankruptcyState>()(() => ({
  event: null,
}));

export function setBankruptcyEvent(event: BankruptcyReset): void {
  useBankruptcyStore.setState({ event });
}

/** User acknowledged the reset modal. */
export function dismissBankruptcy(): void {
  useBankruptcyStore.setState({ event: null });
}

/** Clear on logout so the next session never sees a stale reset. */
export function resetBankruptcy(): void {
  useBankruptcyStore.setState({ event: null });
}
