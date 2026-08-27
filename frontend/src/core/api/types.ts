/**
 * REST DTOs — exact mirrors of the FastAPI response models this app consumes
 * (`backend/app/routers/{auth,orders,portfolio}.py`). The portfolio shapes live in
 * `core/realtime/types.ts` because the `/ws` `portfolio_update` message shares them;
 * they're re-exported here so callers have one import for "the REST surface".
 *
 * Money fields are decimal **strings** on the wire everywhere.
 */

export type {
  HoldingValuation,
  PortfolioSnapshot,
} from "@/core/realtime/types";

/** `GET /auth/me`, and the body of `POST /auth/{register,login}`. */
export interface SessionUser {
  id: string;
  email: string;
  cash_balance: string;
  starting_cash_balance: string;
  /** ISO 8601, UTC */
  created_at: string;
}

export type OrderSide = "buy" | "sell";
export type OrderStatus = "pending" | "filled" | "rejected";

export type RejectionReason =
  | "insufficient_funds"
  | "insufficient_holdings"
  | "stale_price"
  | "pair_not_tradable";

/** `GET /orders` rows and the body of `POST /orders` (201 even when rejected). */
export interface Order {
  id: string;
  symbol: string;
  side: OrderSide;
  status: OrderStatus;
  quantity: string;
  /** set only when `status === "filled"` */
  execution_price: string | null;
  /** set only when `status === "rejected"` */
  rejection_reason: RejectionReason | null;
  /** ISO 8601, UTC */
  created_at: string;
  /** ISO 8601, UTC; set only when `status === "filled"` */
  filled_at: string | null;
}

export interface CreateOrderRequest {
  symbol: string;
  side: OrderSide;
  quantity: string;
}
