/**
 * The order blotter feed — `GET /orders`, newest first, latest 50. Refetched via
 * `mutate("/orders")` after a submission (see the order ticket). Cursor pagination
 * (`?before=`) exists on the backend but the MVP blotter just shows the recent page.
 */

import useSWR, { mutate } from "swr";

import { apiGet } from "@/core/api/client";
import type { Order } from "@/core/api/types";

export const ORDERS_KEY = "/orders";

export interface OrdersFeed {
  orders: Order[] | undefined;
  isLoading: boolean;
  error: unknown;
}

export function useOrders(): OrdersFeed {
  const { data, isLoading, error } = useSWR<Order[]>(
    ORDERS_KEY,
    apiGet<Order[]>,
    { revalidateOnFocus: false },
  );
  return { orders: data, isLoading, error };
}

export function refreshOrders(): void {
  void mutate(ORDERS_KEY);
}
