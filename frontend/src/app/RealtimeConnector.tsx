/**
 * Opens the one market feed for the authenticated session and seeds the first-paint
 * portfolio snapshot. Mounted inside the shell so it only runs once we're past the auth
 * gate.
 *
 * The effect deliberately returns no cleanup: `connectRealtime` is a module-level singleton
 * and the feed should live for the whole session, torn down only on explicit logout
 * (`disconnectRealtime`). Tearing it down on unmount would make StrictMode's mount/unmount/
 * remount abandon a half-open socket, which the in-process backend fan-out does not love.
 */

import { useEffect } from "react";

import { usePortfolioSeed } from "@/core/hooks/usePortfolio";
import { connectRealtime } from "@/core/realtime/connectRealtime";
import { createMockSource } from "@/core/realtime/mockSource";
import {
  IS_BANKRUPT_PREVIEW,
  IS_FROZEN,
  IS_MOCK_MODE,
} from "@/core/realtime/mode";
import { createWebSocketSource } from "@/core/realtime/wsSource";
import { setBankruptcyEvent } from "@/core/state/bankruptcyStore";
import { setConnectionStatus } from "@/core/state/connectionStore";

export function RealtimeConnector() {
  usePortfolioSeed(!IS_MOCK_MODE);

  useEffect(() => {
    if (IS_BANKRUPT_PREVIEW) {
      setBankruptcyEvent({
        type: "bankruptcy_reset",
        starting_cash_balance: "100000.00",
        cleared_symbols: ["BTC", "ETH"],
        reset_at: new Date().toISOString(),
      });
    }
    if (IS_MOCK_MODE) {
      setConnectionStatus("open");
      connectRealtime(createMockSource({ frozen: IS_FROZEN }));
      return;
    }
    connectRealtime(createWebSocketSource());
  }, []);

  return null;
}
