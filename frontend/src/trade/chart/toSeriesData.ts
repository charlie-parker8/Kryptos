import type { CandlestickData, UTCTimestamp } from "lightweight-charts";

import type { Candle } from "@/core/realtime/types";

/**
 * Map wire candles (decimal strings) to lightweight-charts bars. Prices become `number`
 * here — they drive pixel positions only, never authoritative math (same rule as
 * `money.ts`: the wire value stays the source of truth).
 */
export function toSeriesData(
  candles: readonly Candle[],
): CandlestickData<UTCTimestamp>[] {
  return candles.map((c) => ({
    time: c.open_time as UTCTimestamp,
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
  }));
}
