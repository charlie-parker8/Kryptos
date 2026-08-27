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
  useCash,
  useIsConnected,
  useNetWorth,
  usePortfolioAsOf,
} from "@/core/state/selectors";

export interface DashboardData {
  netWorth: string | undefined;
  cash: string | undefined;
  startingCash: string | undefined;
  /** net worth minus the starting balance — the number the whole screen is really about */
  pnlVsStart: Pnl | null;
  connected: boolean;
  asOf: string | undefined;
}

export function useDashboardData(): DashboardData {
  const netWorth = useNetWorth();
  const cash = useCash();
  const asOf = usePortfolioAsOf();
  const connected = useIsConnected();
  const { user } = useSession();

  const startingCash =
    user?.starting_cash_balance ?? (IS_MOCK_MODE ? STARTING_CASH : undefined);

  const pnlVsStart =
    netWorth === undefined || startingCash === undefined
      ? null
      : {
          abs: Number(netWorth) - Number(startingCash),
          pct:
            ((Number(netWorth) - Number(startingCash)) / Number(startingCash)) *
            100,
        };

  return {
    netWorth,
    cash,
    startingCash,
    pnlVsStart,
    connected,
    asOf,
  };
}
