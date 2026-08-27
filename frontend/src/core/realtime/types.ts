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

export type RealtimeMessage = PriceTick | PortfolioUpdate;

/**
 * The one seam between "where messages come from" and the rest of the app. The mock
 * generator implements it now; a real `WebSocket('/ws')` wrapper implements it at
 * integration with no other change. `subscribe` returns its own unsubscribe.
 */
export interface RealtimeSource {
  subscribe(onMessage: (message: RealtimeMessage) => void): () => void;
}
