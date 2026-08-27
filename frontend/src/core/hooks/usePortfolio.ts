/**
 * First-paint portfolio snapshot from `GET /portfolio`, pushed into `portfolioStore` so the
 * dashboard has numbers before the `/ws` stream connects. Once the socket is up its
 * `portfolio_update` messages take over as the live, authoritative source; this stops
 * mattering (hence no focus revalidation). Call `refreshPortfolio()` after an order as a
 * belt-and-braces refetch in case the WS push is delayed.
 */

import { useEffect } from "react";
import useSWR, { mutate } from "swr";

import { apiGet } from "@/core/api/client";
import type { PortfolioSnapshot } from "@/core/api/types";
import { applyPortfolioUpdate } from "@/core/state/portfolioStore";

export const PORTFOLIO_KEY = "/portfolio";

export function usePortfolioSeed(enabled = true): void {
  const { data } = useSWR<PortfolioSnapshot>(
    enabled ? PORTFOLIO_KEY : null,
    apiGet<PortfolioSnapshot>,
    { revalidateOnFocus: false },
  );

  useEffect(() => {
    if (data) applyPortfolioUpdate({ type: "portfolio_update", ...data });
  }, [data]);
}

export function refreshPortfolio(): void {
  void mutate(PORTFOLIO_KEY);
}
