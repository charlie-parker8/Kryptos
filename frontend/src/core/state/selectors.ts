/**
 * Narrow subscription hooks. Every one selects the smallest slice a component needs so a
 * tick re-renders only the leaves that read the changed value (`rerender-defer-reads`).
 */

import { useShallow } from "zustand/react/shallow";

import type {
  Candle,
  CandleInterval,
  Pair,
  PositionValuation,
  PriceTick,
} from "@/core/realtime/types";
import { useAccountStore } from "./accountStore";
import { candleKey, useCandleStore } from "./candleStore";
import { type ConnectionStatus, useConnectionStore } from "./connectionStore";
import { useMarketStore } from "./marketStore";

const NO_CANDLES: readonly Candle[] = Object.freeze([]);

export function useLast(pair: Pair): string | undefined {
  return useMarketStore((s) => s.ticks[pair]?.last);
}

export function useTick(pair: Pair): PriceTick | undefined {
  return useMarketStore((s) => s.ticks[pair]);
}

/** First price seen for this pair since load — the "since open" change reference. */
export function useSessionAnchor(pair: Pair): string | undefined {
  return useMarketStore((s) => s.anchors[pair]);
}

export function useEquity(): string | undefined {
  return useAccountStore((s) => s.snapshot?.equity);
}

export function useFreeCash(): string | undefined {
  return useAccountStore((s) => s.snapshot?.free_cash);
}

export function useTotalUnrealizedPnl(): string | undefined {
  return useAccountStore((s) => s.snapshot?.total_unrealized_pnl);
}

export function useAccountAsOf(): string | undefined {
  return useAccountStore((s) => s.snapshot?.as_of);
}

export function useIsConnected(): boolean {
  return useConnectionStore((s) => s.status === "open");
}

/** Raw feed status — the chart distinguishes "reconnecting" from "closed", `useIsConnected` doesn't. */
export function useConnectionStatus(): ConnectionStatus {
  return useConnectionStore((s) => s.status);
}

/** Live bars for one (pair, interval), ascending by open_time. Stable `[]` when none yet. */
export function useCandleOverlay(
  pair: Pair,
  interval: CandleInterval,
): readonly Candle[] {
  return useCandleStore(
    useShallow((s) => {
      const bars = s.live[candleKey(pair, interval)];
      return bars
        ? Object.values(bars).sort((a, b) => a.open_time - b.open_time)
        : NO_CANDLES;
    }),
  );
}

/** Have we ever received an account snapshot? Drives first-paint skeletons. */
export function useHasAccount(): boolean {
  return useAccountStore((s) => s.snapshot !== null);
}

/** Ids of the open positions, stable-sorted by pair — the list the tables iterate. */
export function useOpenPositionIds(): string[] {
  return useAccountStore(
    useShallow((s) => (s.snapshot?.positions ?? []).map((p) => p.id)),
  );
}

/** The open position on a given pair, if any (one-per-pair on the backend). */
export function usePositionOnPair(pair: Pair): PositionValuation | undefined {
  return useAccountStore((s) =>
    s.snapshot?.positions.find((p) => p.pair === pair),
  );
}

export function usePosition(id: string): PositionValuation | undefined {
  return useAccountStore((s) => s.snapshot?.positions.find((p) => p.id === id));
}
