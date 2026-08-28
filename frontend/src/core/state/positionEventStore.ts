/**
 * The most recent terminal-position event (`position_update`). A liquidation gets a
 * transient toast (the user didn't ask for it and should know); a user close just needs
 * the blotter to refresh. Its own store so only the toast re-renders.
 */

import { create } from "zustand";

import type { PositionUpdate } from "@/core/realtime/types";

interface PositionEventState {
  event: PositionUpdate | null;
}

export const usePositionEventStore = create<PositionEventState>()(() => ({
  event: null,
}));

export function setPositionEvent(event: PositionUpdate): void {
  usePositionEventStore.setState({ event });
}

/** User dismissed the toast. */
export function dismissPositionEvent(): void {
  usePositionEventStore.setState({ event: null });
}

/** Clear on logout. */
export function resetPositionEvent(): void {
  usePositionEventStore.setState({ event: null });
}
