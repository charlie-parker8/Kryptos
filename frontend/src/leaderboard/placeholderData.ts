/**
 * Illustrative standings for `?mock` mode, where there's no backend to serve
 * `GET /leaderboard`. Shape matches the real `LeaderboardEntry` DTO so the screen renders
 * one code path either way.
 */

import type { LeaderboardEntry } from "@/core/api/types";

export const MOCK_STANDINGS: LeaderboardEntry[] = [
  { rank: 1, username: "ada.eth", net_worth: "121908.44", move: 1, is_you: false },
  { rank: 2, username: "satoshi_jr", net_worth: "112442.10", move: 0, is_you: false },
  { rank: 3, username: "you", net_worth: "103465.00", move: 2, is_you: true },
  { rank: 4, username: "paperhands", net_worth: "98001.73", move: -2, is_you: false },
  { rank: 5, username: "hodlr_9000", net_worth: "94455.20", move: -1, is_you: false },
  { rank: 6, username: "diamondhandz", net_worth: "91220.05", move: 0, is_you: false },
  { rank: 7, username: "buyhigh_selllow", net_worth: "88740.90", move: -3, is_you: false },
  { rank: 8, username: "moonboy42", net_worth: "85510.00", move: 1, is_you: false },
];
