/**
 * The handful of derived values the Dashboard needs, in one place — chiefly the "how am I
 * doing vs the cash I started with" math. Starting cash is per-account (`GET /auth/me`),
 * not a constant; in `?mock` mode there's no session, so it falls back to the mock feed's
 * seed value.
 */

import { useSession } from "@/core/auth/useSession";
import type { Pnl } from "@/core/lib/money";
import { IS_MOCK_MODE } from "@/core/realtime/mode";
import { STARTING_CASH } from "@/core/realtime/mockSource";
import {
  useAccountAsOf,
  useEquity,
  useFreeCash,
  useIsConnected,
  useTotalUnrealizedPnl,
} from "@/core/state/selectors";

export interface DashboardData {
  equity: string | undefined;
  freeCash: string | undefined;
  unrealizedPnl: string | undefined;
  startingCash: string | undefined;
  /** equity minus the starting balance — the number the whole screen is really about */
  pnlVsStart: Pnl | null;
  connected: boolean;
  asOf: string | undefined;
}

export function useDashboardData(): DashboardData {
  const equity = useEquity();
  const freeCash = useFreeCash();
  const unrealizedPnl = useTotalUnrealizedPnl();
  const asOf = useAccountAsOf();
  const connected = useIsConnected();
  const { user } = useSession();

  const startingCash =
    user?.starting_cash_balance ?? (IS_MOCK_MODE ? STARTING_CASH : undefined);

  const pnlVsStart =
    equity === undefined || startingCash === undefined
      ? null
      : {
          abs: Number(equity) - Number(startingCash),
          pct:
            ((Number(equity) - Number(startingCash)) / Number(startingCash)) *
            100,
        };

  return {
    equity,
    freeCash,
    unrealizedPnl,
    startingCash,
    pnlVsStart,
    connected,
    asOf,
  };
}
