/**
 * The real `/ws` feed as a `RealtimeSource` — a drop-in for `createMockSource`. The backend
 * pushes `price_tick` (broadcast) and `portfolio_update` (this user's) and never expects a
 * client message, so this only reads. Auth is the `kryptos_session` cookie, sent
 * automatically on the same-origin upgrade (Vite proxies `/ws` to :8000 in dev).
 *
 * Reconnects with capped exponential backoff, mirroring the backend's own
 * `run_price_stream` loop; the backend re-sends a fresh `portfolio_update` on every
 * (re)connect, so no client-side catch-up is needed.
 */

import { setConnectionStatus } from "@/core/state/connectionStore";
import type { RealtimeMessage, RealtimeSource } from "./types";

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

function wsUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws`;
}

function isRealtimeMessage(value: unknown): value is RealtimeMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    ((value as { type: unknown }).type === "price_tick" ||
      (value as { type: unknown }).type === "portfolio_update")
  );
}

export function createWebSocketSource(): RealtimeSource {
  return {
    subscribe(onMessage: (message: RealtimeMessage) => void) {
      let socket: WebSocket | null = null;
      let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
      let backoff = INITIAL_BACKOFF_MS;
      let closed = false;

      const connect = (): void => {
        if (closed) return;
        setConnectionStatus("connecting");
        socket = new WebSocket(wsUrl());

        socket.onopen = () => {
          backoff = INITIAL_BACKOFF_MS;
          setConnectionStatus("open");
        };

        socket.onmessage = (event) => {
          let parsed: unknown;
          try {
            parsed = JSON.parse(event.data as string);
          } catch {
            return;
          }
          if (isRealtimeMessage(parsed)) onMessage(parsed);
        };

        socket.onclose = () => {
          socket = null;
          if (closed) return;
          setConnectionStatus("closed");
          reconnectTimer = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
        };

        // An error is always followed by a close; let onclose own the reconnect.
        socket.onerror = () => {};
      };

      connect();

      return () => {
        closed = true;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        socket?.close();
        setConnectionStatus("closed");
      };
    },
  };
}
