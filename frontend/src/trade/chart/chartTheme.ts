/**
 * lightweight-charts options derived from the app's CSS custom properties, so the chart
 * wears the same "trading desk" palette and re-skins on a theme flip (the canvas can't
 * inherit CSS — `CandleChartCanvas` re-applies these whenever `useTheme()` changes).
 */

import {
  ColorType,
  CrosshairMode,
  type CandlestickSeriesPartialOptions,
  type ChartOptions,
  type DeepPartial,
} from "lightweight-charts";

import { prefersReducedMotion } from "@/core/lib/reducedMotion";
import type { CandleInterval } from "@/core/realtime/types";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function readChartOptions(
  interval: CandleInterval,
): DeepPartial<ChartOptions> {
  const border = cssVar("--k-border");
  const hairline = cssVar("--k-hairline");
  const calm = prefersReducedMotion();
  return {
    layout: {
      background: { type: ColorType.Solid, color: cssVar("--k-surface") },
      textColor: cssVar("--k-muted"),
      fontFamily: cssVar("--k-font-mono"),
      fontSize: 11,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: hairline },
      horzLines: { color: hairline },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: border },
    timeScale: {
      borderColor: border,
      timeVisible: true,
      secondsVisible: interval === 1,
    },
    handleScroll: !calm,
    handleScale: !calm,
  };
}

export function readSeriesColors(): CandlestickSeriesPartialOptions {
  const up = cssVar("--k-up");
  const down = cssVar("--k-down");
  return {
    upColor: up,
    downColor: down,
    wickUpColor: up,
    wickDownColor: down,
    borderVisible: false,
  };
}
