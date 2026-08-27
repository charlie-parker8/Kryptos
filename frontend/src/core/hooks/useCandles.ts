/**
 * OHLC history for the Trade-page chart — `GET /candles?pair=&interval=`, cached and
 * periodically re-fetched (SWR `refreshInterval`, scaled to the timeframe) to reconcile
 * the just-closed bar and heal any gap left by a WS reconnect (the `/ws` feed never
 * replays candle history). The live forming bar is layered on separately via
 * `useCandleOverlay`. In `?mock` mode there's no backend, so this serves illustrative
 * history.
 */

import { useMemo } from "react";
import useSWR, { mutate } from "swr";

import { apiGet } from "@/core/api/client";
import { mockCandleHistory } from "@/core/realtime/mockCandles";
import { IS_MOCK_MODE } from "@/core/realtime/mode";
import type {
  Candle,
  CandleInterval,
  CandlesResponse,
  Pair,
} from "@/core/realtime/types";

const RECONCILE_MS: Record<CandleInterval, number> = {
  1: 15_000,
  5: 30_000,
  15: 60_000,
  60: 120_000,
};

export interface CandlesFeed {
  candles: Candle[] | undefined;
  isLoading: boolean;
  error: unknown;
  refresh: () => void;
}

export function candlesKey(pair: Pair, interval: CandleInterval): string {
  return `/candles?pair=${encodeURIComponent(pair)}&interval=${interval}`;
}

export function useCandles(pair: Pair, interval: CandleInterval): CandlesFeed {
  const key = candlesKey(pair, interval);
  const mock = useMemo(
    () => (IS_MOCK_MODE ? mockCandleHistory(pair, interval) : undefined),
    [pair, interval],
  );

  const { data, isLoading, error } = useSWR<CandlesResponse>(
    IS_MOCK_MODE ? null : key,
    apiGet<CandlesResponse>,
    {
      refreshInterval: RECONCILE_MS[interval],
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
    },
  );

  if (mock) {
    return { candles: mock, isLoading: false, error: null, refresh: () => {} };
  }
  return {
    candles: data?.candles,
    isLoading,
    error,
    refresh: () => void mutate(key),
  };
}
