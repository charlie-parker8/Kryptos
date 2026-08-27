/**
 * The Trade-page candlestick panel: pair + timeframe controls, a REST history seed
 * (`useCandles`) merged with the live forming bar (`useCandleOverlay`), and non-destructive
 * loading / error / stale-feed states layered over the chart so a background refetch or a
 * brief disconnect never blanks it.
 */

import { useMemo } from "react";

import { useCandles } from "@/core/hooks/useCandles";
import { useWallClock } from "@/core/hooks/useWallClock";
import { mergeCandles } from "@/core/lib/candles";
import { formatRelative } from "@/core/lib/format";
import { IS_MOCK_MODE } from "@/core/realtime/mode";
import {
  CANDLE_INTERVALS,
  PAIRS,
  type CandleInterval,
  type Pair,
} from "@/core/realtime/types";
import {
  setChartInterval,
  setChartPair,
  useChartSettingsStore,
} from "@/core/state/chartSettingsStore";
import { useCandleOverlay, useConnectionStatus } from "@/core/state/selectors";

import { CandleChartCanvas } from "./CandleChartCanvas";
import { toSeriesData } from "./toSeriesData";

const INTERVAL_LABEL: Record<CandleInterval, string> = {
  1: "1m",
  5: "5m",
  15: "15m",
  60: "1h",
};

export function PriceChart() {
  const pair = useChartSettingsStore((s) => s.pair);
  const interval = useChartSettingsStore((s) => s.interval);
  const { candles: seed, isLoading, error, refresh } = useCandles(pair, interval);
  const live = useCandleOverlay(pair, interval);
  const status = useConnectionStatus();
  const now = useWallClock(5_000);

  const bars = useMemo(
    () => toSeriesData(mergeCandles(seed ?? [], live)),
    [seed, live],
  );

  const lastBar = bars.at(-1);
  const secondsBehind = lastBar ? now / 1000 - lastBar.time : 0;
  const gapNote =
    !IS_MOCK_MODE && lastBar && secondsBehind > interval * 60 + 90
      ? formatRelative(new Date(lastBar.time * 1000).toISOString(), now)
      : null;

  return (
    <section className="border border-border bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-3 py-2">
        <div className="flex items-center gap-3">
          <label className="sr-only" htmlFor="chart-pair">
            Chart pair
          </label>
          <select
            id="chart-pair"
            value={pair}
            onChange={(e) => setChartPair(e.target.value as Pair)}
            className="rounded-control border border-border bg-bg px-2 py-1 font-mono text-sm text-fg-strong outline-none focus:border-accent"
          >
            {PAIRS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          {status !== "open" ? (
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.08em] text-accent">
              Reconnecting…
            </span>
          ) : gapNote ? (
            <span className="font-mono text-[0.6875rem] text-muted">
              last bar {gapNote}
            </span>
          ) : null}
        </div>
        <div className="flex gap-1">
          {CANDLE_INTERVALS.map((iv) => (
            <button
              key={iv}
              type="button"
              aria-pressed={iv === interval}
              onClick={() => setChartInterval(iv)}
              className={
                iv === interval
                  ? "rounded-control border border-accent bg-accent/10 px-2.5 py-1 font-mono text-xs text-accent"
                  : "rounded-control border border-border px-2.5 py-1 font-mono text-xs text-muted transition-colors hover:text-fg"
              }
            >
              {INTERVAL_LABEL[iv]}
            </button>
          ))}
        </div>
      </header>

      <div className="h-[340px] sm:h-[420px] lg:h-[500px]">
        <ChartBody
          bars={bars}
          interval={interval}
          hasSeed={seed !== undefined}
          isLoading={isLoading}
          hasError={Boolean(error)}
          onRetry={refresh}
        />
      </div>
    </section>
  );
}

interface ChartBodyProps {
  bars: ReturnType<typeof toSeriesData>;
  interval: CandleInterval;
  hasSeed: boolean;
  isLoading: boolean;
  hasError: boolean;
  onRetry: () => void;
}

function ChartBody({
  bars,
  interval,
  hasSeed,
  isLoading,
  hasError,
  onRetry,
}: ChartBodyProps) {
  if (bars.length > 0) {
    return (
      <div className="relative h-full">
        <CandleChartCanvas bars={bars} interval={interval} />
        {hasError ? (
          <div className="absolute right-2 top-2 flex items-center gap-2 border border-border bg-surface-2 px-2 py-1 text-[0.6875rem] text-muted">
            <span>Refresh failed — showing last data.</span>
            <button
              type="button"
              onClick={onRetry}
              className="font-medium text-accent hover:underline"
            >
              Retry
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  if (hasError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted">
        <p>Chart data is unavailable right now.</p>
        <button
          type="button"
          onClick={onRetry}
          className="font-medium text-accent hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (isLoading || !hasSeed) {
    return <div className="h-full w-full animate-pulse bg-surface-2/40" />;
  }

  return (
    <div className="flex h-full items-center justify-center text-sm text-muted">
      No recent candles for this pair.
    </div>
  );
}
