/**
 * The pair + timeframe the Trade-page chart shows — shared with the Order Ticket so both
 * follow one selection, and persisted so a reload keeps it. A stored value is validated
 * against the known pair / interval lists on read; anything unrecognised falls back to the
 * default.
 */

import { create } from "zustand";

import {
  CANDLE_INTERVALS,
  PAIRS,
  type CandleInterval,
  type Pair,
} from "@/core/realtime/types";

const PAIR_KEY = "kryptos:chart:pair:v1";
const INTERVAL_KEY = "kryptos:chart:interval:v1";
const DEFAULT_PAIR: Pair = "BTC/USD";
const DEFAULT_INTERVAL: CandleInterval = 1;

function readStored<T>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return allowed.find((value) => String(value) === raw) ?? fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: string | number): void {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // private mode / storage disabled — the in-memory store still works this session.
  }
}

interface ChartSettings {
  pair: Pair;
  interval: CandleInterval;
}

export const useChartSettingsStore = create<ChartSettings>()(() => ({
  pair: readStored(PAIR_KEY, PAIRS, DEFAULT_PAIR),
  interval: readStored(INTERVAL_KEY, CANDLE_INTERVALS, DEFAULT_INTERVAL),
}));

export function setChartPair(pair: Pair): void {
  persist(PAIR_KEY, pair);
  useChartSettingsStore.setState({ pair });
}

export function setChartInterval(interval: CandleInterval): void {
  persist(INTERVAL_KEY, interval);
  useChartSettingsStore.setState({ interval });
}
