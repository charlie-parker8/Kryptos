/**
 * The handful of derived values every skin's Dashboard needs, in one place. Each skin
 * still lays them out its own way — this just keeps the "how am I doing vs the $100,000
 * start" math from being written three times.
 */

import { STARTING_CASH } from "@/core/realtime/mockSource";
import type { Pnl } from "@/core/lib/money";
import {
  useCash,
  useIsConnected,
  useNetWorth,
  usePortfolioAsOf,
} from "@/core/state/selectors";

export interface DashboardData {
  netWorth: string | undefined;
  cash: string | undefined;
  startingCash: string;
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

  const start = Number(STARTING_CASH);
  const pnlVsStart =
    netWorth === undefined
      ? null
      : {
          abs: Number(netWorth) - start,
          pct: ((Number(netWorth) - start) / start) * 100,
        };

  return {
    netWorth,
    cash,
    startingCash: STARTING_CASH,
    pnlVsStart,
    connected,
    asOf,
  };
}
