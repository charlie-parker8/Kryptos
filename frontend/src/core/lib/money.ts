/**
 * Money + number formatting. The backend is the sole authority on financial math (Decimal,
 * server-side); this module only *displays* the strings it sends and computes cosmetic
 * derived values (unrealised P/L for a holding row, a percent change for a price).
 *
 * Rule from CLAUDE.md: never `parseFloat` a wire value for authoritative arithmetic. Here
 * the exact path is scaled-integer (`toMinor`/`fromMinor`); `Number(...)` is used only for
 * `Intl` formatting and for in-flight tween frames, both explicitly non-authoritative and
 * both safe at these magnitudes (≤ ~$1e7, ≤ 2dp — exact in a double).
 */

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;

/** Scale a decimal string to an integer number of 10^-`dp` units. Throws on malformed input. */
export function toMinor(value: string, dp: number): bigint {
  if (!DECIMAL_RE.test(value))
    throw new Error(`not a decimal string: ${value}`);
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const padded = (fraction + "0".repeat(dp)).slice(0, dp);
  const magnitude = BigInt((whole || "0") + padded);
  return negative ? -magnitude : magnitude;
}

/** Inverse of `toMinor` — integer units back to a decimal string with `dp` fraction digits. */
export function fromMinor(units: bigint, dp: number): string {
  const negative = units < 0n;
  const digits = (negative ? -units : units).toString().padStart(dp + 1, "0");
  const whole = digits.slice(0, digits.length - dp);
  const fraction = dp > 0 ? "." + digits.slice(digits.length - dp) : "";
  return (negative ? "-" : "") + whole + fraction;
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const usdWhole = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

/** "$104,182.55". Accepts the wire string or a tween-frame number. */
export function formatUsd(value: string | number): string {
  return usd.format(typeof value === "string" ? Number(value) : value);
}

/** "$104,183" — for contexts where cents are noise (axis labels, the waterline). */
export function formatUsdWhole(value: string | number): string {
  return usdWhole.format(typeof value === "string" ? Number(value) : value);
}

/** Split into a formatted dollar string and a 2-digit cents string, for statement-style setting. */
export function splitUsd(value: string | number): {
  dollars: string;
  cents: string;
} {
  const [whole = "0", cents = "00"] = (
    typeof value === "string" ? Number(value) : value
  )
    .toFixed(2)
    .split(".");
  return { dollars: usdWhole.format(Number(whole)), cents };
}

/** "+$4,182.55" / "−$310.00" — always signed, for a delta. */
export function formatSignedUsd(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return sign + usd.format(Math.abs(n));
}

/** "+4.18%" / "−0.42%" / "0.00%". `value` is already a percentage, not a ratio. */
export function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

/** Trim a quantity string to its pair's display precision, dropping trailing zeros. */
export function formatQty(value: string, precision: number): string {
  const n = Number(value);
  if (n === 0) return "0";
  return n.toFixed(precision).replace(/\.?0+$/, "");
}

/** Percent change between two wire prices, as a percentage figure. */
export function pctChange(from: string, to: string): number {
  const base = Number(from);
  if (base === 0) return 0;
  return ((Number(to) - base) / base) * 100;
}

export interface Pnl {
  /** absolute unrealised gain/loss in USD */
  abs: number;
  /** as a percent of cost basis */
  pct: number;
}

/** Unrealised P/L for one holding: market value minus cost basis (avg cost × quantity). */
export function unrealizedPnl(
  averageCost: string,
  quantity: string,
  marketValue: string | null,
): Pnl | null {
  if (marketValue === null) return null;
  const costBasisMinor = toMinor(averageCost, 8) * toMinor(quantity, 10); // scale 10^-18
  const valueMinor = toMinor(marketValue, 2) * 10n ** 16n; // lift to scale 10^-18
  const diffMinor = valueMinor - costBasisMinor;
  const abs = Number(fromMinor(diffMinor, 18));
  const costBasis = Number(fromMinor(costBasisMinor, 18));
  return { abs, pct: costBasis === 0 ? 0 : (abs / costBasis) * 100 };
}
