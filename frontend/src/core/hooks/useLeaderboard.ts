/**
 * The leaderboard feed — `GET /leaderboard`, polled every few seconds (SWR
 * `refreshInterval`) since rankings drift as the market moves and there's no WS push for
 * them. In `?mock` mode there's no backend, so it serves the illustrative standings.
 */

import useSWR from "swr";

import { apiGet } from "@/core/api/client";
import type { LeaderboardEntry, LeaderboardResponse } from "@/core/api/types";
import { IS_MOCK_MODE } from "@/core/realtime/mode";
import { MOCK_STANDINGS } from "@/leaderboard/placeholderData";

export const LEADERBOARD_KEY = "/leaderboard";
const REFRESH_MS = 5_000;

export interface LeaderboardFeed {
  standings: LeaderboardEntry[] | undefined;
  /** the viewer's own row when they rank below the returned page; null otherwise */
  you: LeaderboardEntry | null;
  isLoading: boolean;
  error: unknown;
}

export function useLeaderboard(): LeaderboardFeed {
  const { data, isLoading, error } = useSWR<LeaderboardResponse>(
    IS_MOCK_MODE ? null : LEADERBOARD_KEY,
    apiGet<LeaderboardResponse>,
    { refreshInterval: REFRESH_MS, revalidateOnFocus: false },
  );

  if (IS_MOCK_MODE) {
    return { standings: MOCK_STANDINGS, you: null, isLoading: false, error: null };
  }

  return {
    standings: data?.entries,
    you: data?.you ?? null,
    isLoading,
    error,
  };
}
