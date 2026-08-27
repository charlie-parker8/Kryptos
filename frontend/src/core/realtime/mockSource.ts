/**
 * Fake market feed for the prototypes. Emits messages in the *exact* shape of the backend
 * `/ws` stream (`price_tick`, `portfolio_update`) so the eventual real
 * `WebSocket('/ws')` wrapper is a drop-in replacement behind `RealtimeSource`.
 *
 * All prices/levels here are illustrative, not real market data.
 */

import type {
  Asset,
  Pair,
  PortfolioUpdate,
  PriceTick,
  RealtimeMessage,
  RealtimeSource,
} from "./types";
import { PAIRS } from "./types";

export const STARTING_CASH = "100000.00";

interface MockHolding {
  symbol: Asset;
  quantity: string;
  average_cost: string;
}

/**
 * Seeded so a mock session always tells the same story: net worth a little above the
 * $100,000 start (~+3.5%), one clear winner per position, room left in cash.
 */
const MOCK_CASH = "33380.00";
const MOCK_HOLDINGS: MockHolding[] = [
  { symbol: "BTC", quantity: "0.5000000000", average_cost: "91000.00000000" },
  { symbol: "ETH", quantity: "6.4000000000", average_cost: "3300.00000000" },
];

const SEED_PRICE: Record<Pair, number> = {
  "BTC/USD": 95204.1,
  "ETH/USD": 3512.9,
  "SOL/USD": 198.44,
};

const PER_TICK_VOL: Record<Pair, number> = {
  "BTC/USD": 0.0006,
  "ETH/USD": 0.0009,
  "SOL/USD": 0.0016,
};

interface MockOptions {
  /** Emit one deterministic round of ticks + a portfolio update, then stop. For screenshots. */
  frozen?: boolean;
  /** Base interval between ticks, ms (jittered ±40%). Ignored when frozen. */
  intervalMs?: number;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(rng: () => number): number {
  const u = 1 - rng();
  const v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const ASSET_OF: Record<Pair, Asset> = {
  "BTC/USD": "BTC",
  "ETH/USD": "ETH",
  "SOL/USD": "SOL",
};

export function createMockSource(options: MockOptions = {}): RealtimeSource {
  const { frozen = false, intervalMs = 260 } = options;

  return {
    subscribe(onMessage: (message: RealtimeMessage) => void) {
      const rng = mulberry32(frozen ? 0x5eed : Date.now() >>> 0);
      const last: Record<Pair, number> = { ...SEED_PRICE };
      const staleUntil: Record<Pair, number> = {
        "BTC/USD": 0,
        "ETH/USD": 0,
        "SOL/USD": 0,
      };
      let timer: ReturnType<typeof setTimeout> | undefined;
      let stopped = false;
      let tickCount = 0;

      const emitTick = (pair: Pair): PriceTick => {
        const price = last[pair];
        const spread = price * 0.0002;
        const now = Date.now();
        const aged = now < staleUntil[pair];
        return {
          type: "price_tick",
          pair,
          bid: (price - spread / 2).toFixed(2),
          ask: (price + spread / 2).toFixed(2),
          last: price.toFixed(2),
          as_of: new Date(aged ? now - 14_000 : now).toISOString(),
          broadcast_at: now,
        };
      };

      const buildPortfolio = (): PortfolioUpdate => {
        let marketTotal = 0;
        const holdings = MOCK_HOLDINGS.map((h) => {
          const pair = `${h.symbol}/USD` as Pair;
          const price = last[pair];
          const value = price * Number(h.quantity);
          marketTotal += value;
          return {
            symbol: h.symbol,
            quantity: h.quantity,
            average_cost: h.average_cost,
            current_price: price.toFixed(2),
            market_value: value.toFixed(2),
            stale: Date.now() < staleUntil[pair],
          };
        });
        // SOL: held-universe pair with no position — shown so the empty row has a place.
        holdings.push({
          symbol: "SOL",
          quantity: "0",
          average_cost: "0",
          current_price: last["SOL/USD"].toFixed(2),
          market_value: "0.00",
          stale: false,
        });
        const netWorth = Number(MOCK_CASH) + marketTotal;
        return {
          type: "portfolio_update",
          cash_balance: MOCK_CASH,
          holdings,
          net_worth: netWorth.toFixed(2),
          as_of: new Date().toISOString(),
        };
      };

      const step = (pair: Pair): void => {
        const seed = SEED_PRICE[pair];
        const drift =
          gaussian(rng) * PER_TICK_VOL[pair] +
          ((seed - last[pair]) / seed) * 0.015;
        last[pair] = last[pair] * (1 + drift);
      };

      // Initial snapshot + one tick per pair, immediately — matches a real client getting
      // the last portfolio_update on connect and the cached prices right after.
      onMessage(buildPortfolio());
      for (const pair of PAIRS) onMessage(emitTick(pair));

      if (frozen) {
        for (const pair of PAIRS) {
          step(pair);
          onMessage(emitTick(pair));
        }
        onMessage(buildPortfolio());
        return () => {};
      }

      const scheduleNext = (): void => {
        const jitter = 0.6 + rng() * 0.8;
        timer = setTimeout(run, intervalMs * jitter);
      };
      const run = (): void => {
        if (stopped) return;
        const pair = PAIRS[Math.floor(rng() * PAIRS.length)] as Pair;

        // Every ~150 ticks, let one pair go stale for a spell so the stale UI is reachable.
        tickCount += 1;
        if (tickCount % 150 === 0) {
          staleUntil[pair] = Date.now() + 16_000;
        }

        step(pair);
        onMessage(emitTick(pair));
        if (MOCK_HOLDINGS.some((h) => ASSET_OF[pair] === h.symbol)) {
          onMessage(buildPortfolio());
        }
        scheduleNext();
      };
      scheduleNext();

      return () => {
        stopped = true;
        if (timer) clearTimeout(timer);
      };
    },
  };
}
