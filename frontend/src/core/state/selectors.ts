/**
 * Narrow subscription hooks. Every one selects the smallest slice a component needs so a
 * tick re-renders only the leaves that read the changed value (`rerender-defer-reads`).
 */

import { useShallow } from "zustand/react/shallow";

import type {
  Asset,
  Candle,
  CandleInterval,
  HoldingValuation,
  Pair,
  PriceTick,
} from "@/core/realtime/types";
import { candleKey, useCandleStore } from "./candleStore";
import { type ConnectionStatus, useConnectionStore } from "./connectionStore";
import { useMarketStore } from "./marketStore";
import { usePortfolioStore } from "./portfolioStore";

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

export function useNetWorth(): string | undefined {
  return usePortfolioStore((s) => s.snapshot?.net_worth);
}

export function useCash(): string | undefined {
  return usePortfolioStore((s) => s.snapshot?.cash_balance);
}

export function usePortfolioAsOf(): string | undefined {
  return usePortfolioStore((s) => s.snapshot?.as_of);
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

/** Have we ever received a portfolio snapshot? Drives first-paint skeletons. */
export function useHasPortfolio(): boolean {
  return usePortfolioStore((s) => s.snapshot !== null);
}

export function useHoldingSymbols(): Asset[] {
  return usePortfolioStore(
    useShallow((s) => (s.snapshot?.holdings ?? []).map((h) => h.symbol)),
  );
}

export function useHolding(symbol: Asset): HoldingValuation | undefined {
  return usePortfolioStore((s) =>
    s.snapshot?.holdings.find((h) => h.symbol === symbol),
  );
}
