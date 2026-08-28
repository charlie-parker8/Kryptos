/**
 * Exact TypeScript mirrors of the two messages the backend pushes over `GET /ws`
 * (`backend/app/ws_messages.py` + `backend/app/portfolio.py`) and the REST DTOs the
 * integration phase will consume. Money is a decimal **string** on the wire everywhere —
 * never parse it to a float for arithmetic. `broadcast_at` is the one numeric field
 * (unix ms), and only `price_tick` carries it.
 */

export const PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"] as const;
export type Pair = (typeof PAIRS)[number];

/** Leverage presets — mirrors `KRYPTOS_LEVERAGE_PRESETS` (backend config). */
export const LEVERAGE_PRESETS = [2, 5, 10] as const;
export type Leverage = (typeof LEVERAGE_PRESETS)[number];

/** Minimum collateral per position, USD — mirrors `KRYPTOS_MIN_COLLATERAL`. */
export const MIN_COLLATERAL = 10;

/** Base asset as it appears in ledger rows, e.g. "BTC" (not the pair). */
export type Asset = "BTC" | "ETH" | "SOL";

/**
 * Candlestick timeframes, in minutes — mirrors the backend `supported_candle_intervals`
 * (`backend/app/config.py`). Kept in sync by hand, like the message shapes below.
 */
export const CANDLE_INTERVALS = [1, 5, 15, 60] as const;
export type CandleInterval = (typeof CANDLE_INTERVALS)[number];

export interface PriceTick {
  type: "price_tick";
  pair: Pair;
  bid: string;
  ask: string;
  last: string;
  /** ISO 8601, UTC. Server fetch time (Kraken ticker carries no timestamp). */
  as_of: string;
  /** unix epoch milliseconds — the Milestone-A tick-to-client latency marker. */
  broadcast_at: number;
}

export type PositionSide = "long" | "short";
export type PositionStatus = "open" | "closed" | "liquidated";
export type CloseReason = "user" | "liquidation" | "bankruptcy";

/**
 * One open position as the server values it (`GET /portfolio` and the `account_update` WS
 * message). Mirrors `PositionValuation` (`backend/app/account.py`). Money is a decimal
 * string; `mark_price` / `unrealized_pnl` / `position_equity` / `margin_ratio` are null
 * only when no price has ever been observed for the pair.
 */
export interface PositionValuation {
  id: string;
  pair: Pair;
  side: PositionSide;
  leverage: number;
  collateral: string;
  size: string;
  entry_price: string;
  liquidation_price: string;
  mark_price: string | null;
  unrealized_pnl: string | null;
  position_equity: string | null;
  margin_ratio: string | null;
  /** true when the mark is older than the max age, or has never been observed */
  stale: boolean;
}

export interface AccountSnapshot {
  free_cash: string;
  equity: string;
  total_unrealized_pnl: string;
  positions: PositionValuation[];
  /** ISO 8601, UTC — server compute time */
  as_of: string;
}

export interface AccountUpdate extends AccountSnapshot {
  type: "account_update";
}

/**
 * Sent to a user's own connections when a position reaches a terminal state — a user
 * close, an automatic liquidation, or a bankruptcy reset. Drives the blotter refresh and
 * (for liquidations) a toast. An `account_update` with the new balances follows.
 */
export interface PositionUpdate {
  type: "position_update";
  position_id: string;
  pair: Pair;
  side: PositionSide;
  status: "closed" | "liquidated";
  close_price: string;
  realized_pnl: string;
  reason: CloseReason;
  /** ISO 8601, UTC */
  at: string;
}

/**
 * Sent to a user's own connections when their account equity hit the floor and the account
 * was reset (backend `app/bankruptcy.py`). A `position_update` per closed position and an
 * `account_update` with the restored balance follow.
 */
export interface BankruptcyReset {
  type: "bankruptcy_reset";
  /** the balance the account was restored to, decimal string */
  starting_cash_balance: string;
  /** pairs whose positions were closed by the reset, e.g. ["BTC/USD", "ETH/USD"] */
  closed_positions: string[];
  /** ISO 8601, UTC */
  reset_at: string;
}

/**
 * One OHLC bar. Mirrors `CandlePoint` from `GET /candles` (backend
 * `app/routers/candles.py`). Prices are decimal **strings** — never float them for
 * arithmetic; the chart only ever `Number()`s them for pixel positions.
 */
export interface Candle {
  /** unix epoch **seconds** — the bucket's open time (lightweight-charts `time`). */
  open_time: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

/** `GET /candles?pair=&interval=` response. `candles` ascending by `open_time`; the last
 * entry may still be forming. */
export interface CandlesResponse {
  pair: Pair;
  interval: CandleInterval;
  candles: Candle[];
}

/**
 * Live bar pushed over `/ws` for whichever (pair, interval) chart is open — broadcast to
 * every client (like `price_tick`), filtered client-side. Mirrors `CandleUpdateMessage`
 * (backend `app/ws_messages.py`). `closed` is true on the frame that finalises a bucket.
 */
export interface CandleUpdate {
  type: "candle_update";
  pair: Pair;
  interval: CandleInterval;
  /** unix epoch seconds — the bucket's open time. */
  open_time: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  closed: boolean;
  /** unix epoch milliseconds. */
  broadcast_at: number;
}

export type RealtimeMessage =
  | PriceTick
  | AccountUpdate
  | PositionUpdate
  | BankruptcyReset
  | CandleUpdate;

/**
 * The one seam between "where messages come from" and the rest of the app. The mock
 * generator implements it now; a real `WebSocket('/ws')` wrapper implements it at
 * integration with no other change. `subscribe` returns its own unsubscribe.
 */
export interface RealtimeSource {
  subscribe(onMessage: (message: RealtimeMessage) => void): () => void;
}
