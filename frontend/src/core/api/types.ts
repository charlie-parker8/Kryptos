/**
 * REST DTOs — exact mirrors of the FastAPI response models this app consumes
 * (`backend/app/routers/{auth,positions,portfolio,leaderboard}.py`). The account shapes
 * live in `core/realtime/types.ts` because the `/ws` `account_update` message shares them;
 * they're re-exported here so callers have one import for "the REST surface".
 *
 * Money fields are decimal **strings** on the wire everywhere.
 */

export type {
  AccountSnapshot,
  PositionSide,
  PositionStatus,
  PositionValuation,
} from "@/core/realtime/types";

/** `GET /auth/me`, and the body of `POST /auth/{register,login}`. */
export interface SessionUser {
  id: string;
  email: string;
  /** unique, chosen at registration; the leaderboard's display name */
  username: string;
  /** free cash — USD not committed as collateral to an open position */
  cash_balance: string;
  starting_cash_balance: string;
  /** ISO 8601, UTC */
  created_at: string;
}

/** `GET /leaderboard`. Money fields are decimal strings; `move` and `rank` are numbers. */
export interface LeaderboardEntry {
  rank: number;
  username: string;
  /** account equity — free cash + Σ(open position collateral + unrealized P&L). Can be negative. */
  equity: string;
  /** previous rank minus current rank: positive = climbed, negative = fell, 0 = new/unchanged */
  move: number;
  is_you: boolean;
}

export interface LeaderboardResponse {
  entries: LeaderboardEntry[];
  /** the viewer's own row, present only when they rank below `entries` */
  you: LeaderboardEntry | null;
  /** ISO 8601, UTC */
  as_of: string;
}

export type PositionCloseReason = "user" | "liquidation" | "bankruptcy";

/** Why `POST /positions` said no — mapped to per-reason copy in the ticket. */
export type OpenRejectionReason =
  | "leverage_not_allowed"
  | "below_min_collateral"
  | "position_exists"
  | "insufficient_free_cash"
  | "stale_price"
  | "pair_not_tradable";

/** `GET /positions` rows and the body of `POST /positions` / `POST /positions/{id}/close`. */
export interface Position {
  id: string;
  pair: string;
  side: "long" | "short";
  status: "open" | "closed" | "liquidated";
  leverage: number;
  collateral: string;
  size: string;
  entry_price: string;
  liquidation_price: string;
  open_fee: string;
  close_price: string | null;
  close_fee: string | null;
  realized_pnl: string | null;
  close_reason: PositionCloseReason | null;
  /** ISO 8601, UTC */
  opened_at: string;
  /** ISO 8601, UTC; set only when terminal */
  closed_at: string | null;
}

export interface OpenPositionRequest {
  pair: string;
  side: "long" | "short";
  /** USD collateral to commit, decimal string, <= 2 dp */
  collateral: string;
  leverage: number;
}
