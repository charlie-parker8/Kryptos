/**
 * Narrow subscription hooks. Every one selects the smallest slice a component needs so a
 * tick re-renders only the leaves that read the changed value (`rerender-defer-reads`).
 */

import { useShallow } from "zustand/react/shallow";

import type {
  Asset,
  HoldingValuation,
  Pair,
  PriceTick,
} from "@/core/realtime/types";
import { useMarketStore } from "./marketStore";
import { usePortfolioStore } from "./portfolioStore";

export function useLast(pair: Pair): string | undefined {
  return useMarketStore((s) => s.ticks[pair]?.last);
}

export function useTick(pair: Pair): PriceTick | undefined {
  return useMarketStore((s) => s.ticks[pair]);
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
