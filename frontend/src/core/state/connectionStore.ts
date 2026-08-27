/**
 * Live-feed connection status, driven by the realtime source (`wsSource.ts`). Separate from
 * the portfolio store so the `LiveDot` in the header reflects the actual socket state, not
 * "have we received a snapshot yet". The mock source reports `"open"` immediately.
 */

import { create } from "zustand";

export type ConnectionStatus = "connecting" | "open" | "closed";

interface ConnectionState {
  status: ConnectionStatus;
}

export const useConnectionStore = create<ConnectionState>()(() => ({
  status: "connecting",
}));

export function setConnectionStatus(status: ConnectionStatus): void {
  if (useConnectionStore.getState().status !== status) {
    useConnectionStore.setState({ status });
  }
}
