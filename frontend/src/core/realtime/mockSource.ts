/**
 * Fake market feed for the prototypes. Emits messages in the *exact* shape of the backend
 * `/ws` stream (`price_tick`, `account_update`, `candle_update`) so the real
 * `WebSocket('/ws')` wrapper is a drop-in replacement behind `RealtimeSource`.
 *
 * All prices/levels here are illustrative, not real market data.
 */

import { previewLiquidationPrice } from "@/core/lib/money";
import { mockCandleUpdate } from "./mockCandles";
import { gaussian, mulberry32 } from "./mockRng";
import type {
  AccountUpdate,
  Pair,
  PositionSide,
  PositionValuation,
  PriceTick,
  RealtimeMessage,
  RealtimeSource,
} from "./types";
import { CANDLE_INTERVALS, PAIRS } from "./types";

export const STARTING_CASH = "10000.00";

interface MockPositionSeed {
  id: string;
  pair: Pair;
  side: PositionSide;
  leverage: number;
  collateral: number;
  entry: number;
}

/**
 * Seeded so a mock session always tells the same story: a winning BTC long, a losing ETH
 * short, ~half the balance still free.
 */
const MOCK_FREE_CASH = 6000;
const MOCK_POSITIONS: MockPositionSeed[] = [
  {
    id: "mock-btc-long",
    pair: "BTC/USD",
    side: "long",
    leverage: 5,
    collateral: 2500,
    entry: 91000,
  },
  {
    id: "mock-eth-short",
    pair: "ETH/USD",
    side: "short",
    leverage: 10,
    collateral: 1500,
    entry: 3300,
  },
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
  /** Emit one deterministic round of ticks + an account update, then stop. For screenshots. */
  frozen?: boolean;
  /** Base interval between ticks, ms (jittered ±40%). Ignored when frozen. */
  intervalMs?: number;
}

const ASSET_HELD_ON: Set<Pair> = new Set(MOCK_POSITIONS.map((p) => p.pair));

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

      const valuePosition = (seed: MockPositionSeed): PositionValuation => {
        const mark = last[seed.pair];
        const notional = seed.collateral * seed.leverage;
        const size = notional / seed.entry;
        const upnl =
          seed.side === "long"
            ? size * (mark - seed.entry)
            : size * (seed.entry - mark);
        const equity = seed.collateral + upnl;
        return {
          id: seed.id,
          pair: seed.pair,
          side: seed.side,
          leverage: seed.leverage,
          collateral: seed.collateral.toFixed(2),
          size: size.toFixed(10),
          entry_price: seed.entry.toFixed(8),
          liquidation_price: (
            previewLiquidationPrice(seed.side, String(seed.entry), seed.leverage) ??
            0
          ).toFixed(8),
          mark_price: mark.toFixed(2),
          unrealized_pnl: upnl.toFixed(2),
          position_equity: equity.toFixed(2),
          margin_ratio: (equity / notional).toFixed(6),
          stale: Date.now() < staleUntil[seed.pair],
        };
      };

      const buildAccount = (): AccountUpdate => {
        const positions = MOCK_POSITIONS.map(valuePosition);
        const openEquity = positions.reduce(
          (sum, p) => sum + Number(p.position_equity),
          0,
        );
        const totalUpnl = positions.reduce(
          (sum, p) => sum + Number(p.unrealized_pnl),
          0,
        );
        return {
          type: "account_update",
          free_cash: MOCK_FREE_CASH.toFixed(2),
          equity: (MOCK_FREE_CASH + openEquity).toFixed(2),
          total_unrealized_pnl: totalUpnl.toFixed(2),
          positions,
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

      const emitCandles = (pair: Pair): void => {
        for (const interval of CANDLE_INTERVALS) {
          onMessage(mockCandleUpdate(pair, interval, last[pair]));
        }
      };

      onMessage(buildAccount());
      for (const pair of PAIRS) {
        onMessage(emitTick(pair));
        emitCandles(pair);
      }

      if (frozen) {
        for (const pair of PAIRS) {
          step(pair);
          onMessage(emitTick(pair));
          emitCandles(pair);
        }
        onMessage(buildAccount());
        return () => {};
      }

      const scheduleNext = (): void => {
        const jitter = 0.6 + rng() * 0.8;
        timer = setTimeout(run, intervalMs * jitter);
      };
      const run = (): void => {
        if (stopped) return;
        const pair = PAIRS[Math.floor(rng() * PAIRS.length)] as Pair;

        tickCount += 1;
        if (tickCount % 150 === 0) {
          staleUntil[pair] = Date.now() + 16_000;
        }

        step(pair);
        onMessage(emitTick(pair));
        emitCandles(pair);
        if (ASSET_HELD_ON.has(pair)) {
          onMessage(buildAccount());
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
