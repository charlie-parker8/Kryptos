/**
 * The position blotter feed — `GET /positions`, newest first. Refetched via
 * `mutate(POSITIONS_KEY)` after an open or close (see the position ticket / open-positions
 * panel). Cursor pagination (`?before=`) exists on the backend; the MVP blotter shows the
 * recent page only.
 */

import useSWR, { mutate } from "swr";

import { apiGet } from "@/core/api/client";
import type { Position } from "@/core/api/types";

export const POSITIONS_KEY = "/positions?status=all";

export interface PositionsFeed {
  positions: Position[] | undefined;
  isLoading: boolean;
  error: unknown;
}

export function usePositions(): PositionsFeed {
  const { data, isLoading, error } = useSWR<Position[]>(
    POSITIONS_KEY,
    apiGet<Position[]>,
    { revalidateOnFocus: false },
  );
  return { positions: data, isLoading, error };
}

export function refreshPositions(): void {
  void mutate(POSITIONS_KEY);
}
