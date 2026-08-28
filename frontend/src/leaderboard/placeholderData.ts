/**
 * Illustrative standings for `?mock` mode, where there's no backend to serve
 * `GET /leaderboard`. Shape matches the real `LeaderboardEntry` DTO so the screen renders
 * one code path either way. Equity can be negative — a leveraged account that got caught
 * on the wrong side of a gap move.
 */

import type { LeaderboardEntry } from "@/core/api/types";

export const MOCK_STANDINGS: LeaderboardEntry[] = [
  { rank: 1, username: "ada.eth", equity: "31908.44", move: 1, is_you: false },
  { rank: 2, username: "satoshi_jr", equity: "22442.10", move: 0, is_you: false },
  { rank: 3, username: "you", equity: "13465.00", move: 2, is_you: true },
  { rank: 4, username: "paperhands", equity: "8001.73", move: -2, is_you: false },
  { rank: 5, username: "hodlr_9000", equity: "4455.20", move: -1, is_you: false },
  { rank: 6, username: "degen_maxi", equity: "1220.05", move: 0, is_you: false },
  { rank: 7, username: "buyhigh_selllow", equity: "410.90", move: -3, is_you: false },
  { rank: 8, username: "rekt_again", equity: "-320.00", move: 1, is_you: false },
];
