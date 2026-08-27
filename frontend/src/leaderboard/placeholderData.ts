/**
 * Illustrative standings for the leaderboard placeholder. There is no `GET /leaderboard`
 * endpoint yet (the Redis-backed leaderboard is a later backend phase); until it ships the
 * screen shows these clearly-labelled fake figures so the layout is real and reviewable.
 */

export interface Standing {
  rank: number;
  handle: string;
  netWorth: string;
  /** rank change since the last snapshot: + up, - down, 0 unchanged */
  move: number;
  isYou?: boolean;
}

export const MOCK_STANDINGS: Standing[] = [
  { rank: 1, handle: "ada.eth", netWorth: "121908.44", move: 1 },
  { rank: 2, handle: "satoshi_jr", netWorth: "112442.10", move: 0 },
  { rank: 3, handle: "you", netWorth: "103465.00", move: 2, isYou: true },
  { rank: 4, handle: "paperhands", netWorth: "98001.73", move: -2 },
  { rank: 5, handle: "hodlr_9000", netWorth: "94455.20", move: -1 },
  { rank: 6, handle: "diamondhandz", netWorth: "91220.05", move: 0 },
  { rank: 7, handle: "buyhigh_selllow", netWorth: "88740.90", move: -3 },
  { rank: 8, handle: "moonboy42", netWorth: "85510.00", move: 1 },
];
