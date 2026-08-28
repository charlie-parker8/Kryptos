/**
 * Thin imperative wrapper around lightweight-charts v5. Owns the chart instance for its
 * lifetime; props flow in through `setData` / `applyOptions` so React never re-creates the
 * canvas. The container **must** have a definite height (the parent sets it) — `autoSize`
 * measures the element and collapses to 0 otherwise.
 */

import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { CandleInterval } from "@/core/realtime/types";
import { useTheme } from "@/theme";

import { readChartOptions, readSeriesColors } from "./chartTheme";

interface Props {
  bars: CandlestickData<UTCTimestamp>[];
  interval: CandleInterval;
}

// Bars visible when a timeframe first loads — a wide-angle view, not the tight cluster
// lightweight-charts' default bar spacing would show. Older history stays a scroll away.
const DEFAULT_VISIBLE_BARS = 160;

export function CandleChartCanvas({ bars, interval }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const seededIntervalRef = useRef<CandleInterval | null>(null);
  const theme = useTheme();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Seed the real container size so the first visible-range calc isn't racing the
    // ResizeObserver autoSize uses (a 0-width first frame sticks as wrong bar spacing).
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight,
      autoSize: true,
    });
    chartRef.current = chart;
    seriesRef.current = chart.addSeries(CandlestickSeries);
    seededIntervalRef.current = null;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Palette + timeframe-dependent axis options; re-applied on a theme flip (the canvas
  // can't inherit CSS custom properties).
  useEffect(() => {
    chartRef.current?.applyOptions(readChartOptions(interval));
    seriesRef.current?.applyOptions(readSeriesColors());
  }, [interval, theme]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    const timeScale = chart.timeScale();
    const freshTimeframe = seededIntervalRef.current !== interval;
    const priorRange = freshTimeframe ? null : timeScale.getVisibleLogicalRange();
    series.setData(bars);
    if (priorRange) {
      timeScale.setVisibleLogicalRange(priorRange);
    } else if (bars.length > DEFAULT_VISIBLE_BARS) {
      timeScale.setVisibleLogicalRange({
        from: bars.length - DEFAULT_VISIBLE_BARS,
        to: bars.length + 3, // a few bars of right margin
      });
    } else {
      timeScale.fitContent();
    }
    seededIntervalRef.current = interval;
    containerRef.current?.setAttribute("data-chart-ready", "1");
  }, [bars, interval]);

  return <div ref={containerRef} className="h-full w-full" />;
}
