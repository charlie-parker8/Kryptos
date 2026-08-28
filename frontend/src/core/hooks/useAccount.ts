/**
 * First-paint account snapshot from `GET /portfolio`, pushed into `accountStore` so the
 * dashboard has numbers before the `/ws` stream connects. Once the socket is up its
 * `account_update` messages take over as the live, authoritative source (hence no focus
 * revalidation). Call `refreshAccount()` after opening/closing a position as a
 * belt-and-braces refetch in case the WS push is delayed.
 */

import { useEffect } from "react";
import useSWR, { mutate } from "swr";

import { apiGet } from "@/core/api/client";
import type { AccountSnapshot } from "@/core/api/types";
import { applyAccountUpdate } from "@/core/state/accountStore";

export const ACCOUNT_KEY = "/portfolio";

export function useAccountSeed(enabled = true): void {
  const { data } = useSWR<AccountSnapshot>(
    enabled ? ACCOUNT_KEY : null,
    apiGet<AccountSnapshot>,
    { revalidateOnFocus: false },
  );

  useEffect(() => {
    if (data) applyAccountUpdate({ type: "account_update", ...data });
  }, [data]);
}

export function refreshAccount(): void {
  void mutate(ACCOUNT_KEY);
}
