/**
 * Exact TypeScript mirrors of the two messages the backend pushes over `GET /ws`
 * (`backend/app/ws_messages.py` + `backend/app/portfolio.py`) and the REST DTOs the
 * integration phase will consume. Money is a decimal **string** on the wire everywhere —
 * never parse it to a float for arithmetic. `broadcast_at` is the one numeric field
 * (unix ms), and only `price_tick` carries it.
 */

export const PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"] as const;
export type Pair = (typeof PAIRS)[number];

/** Base asset as it appears in holdings/ledger rows, e.g. "BTC" (not the pair). */
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

export interface HoldingValuation {
  /** base asset, e.g. "BTC" */
  symbol: Asset;
  quantity: string;
  average_cost: string;
  /** the pair's last price; null if never observed / provider down */
  current_price: string | null;
  /** current_price * quantity, 2dp; null when current_price is null */
  market_value: string | null;
  /** true when the price is older than the max age, or is null */
  stale: boolean;
}

export interface PortfolioSnapshot {
  cash_balance: string;
  holdings: HoldingValuation[];
  net_worth: string;
  /** ISO 8601, UTC — server compute time */
  as_of: string;
}

export interface PortfolioUpdate extends PortfolioSnapshot {
  type: "portfolio_update";
}

/**
 * Sent once to a user's own connections when their net worth hit $0 and the account was
 * reset (backend `app/bankruptcy.py`). A `portfolio_update` with the restored balances
 * follows immediately after.
 */
export interface BankruptcyReset {
  type: "bankruptcy_reset";
  /** the balance the account was restored to, decimal string */
  starting_cash_balance: string;
  /** base assets whose positions were cleared, e.g. ["BTC", "ETH"] */
  cleared_symbols: string[];
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
  | PortfolioUpdate
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
