import { formatUsd } from "@/core/lib/money";
import { Skeleton } from "@/core/primitives/Skeleton";
import { LEVERAGE_PRESETS } from "@/core/realtime/types";
import { useDashboardData } from "@/core/useDashboardData";
import {
  useHasAccount,
  useOpenPositionIds,
  usePosition,
} from "@/core/state/selectors";

const MAX_LEVERAGE = Math.max(...LEVERAGE_PRESETS);
const FULL_BAR_AT_PCT = 40; // mark this far from liq → full bar

function distanceToLiqPct(mark: string | null, liq: string): number | null {
  if (mark === null) return null;
  const m = Number(mark);
  const l = Number(liq);
  if (!Number.isFinite(m) || !Number.isFinite(l) || m === 0) return null;
  return (Math.abs(m - l) / m) * 100;
}

export function MarginHealth() {
  const hasAccount = useHasAccount();
  const ids = useOpenPositionIds();
  const { freeCash } = useDashboardData();

  return (
    <article className="border border-border p-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
        Margin health
      </h3>
      {!hasAccount ? (
        <div className="mt-3 space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      ) : ids.length === 0 ? (
        <BuyingPower freeCash={freeCash} />
      ) : (
        <ul className="mt-3 space-y-2.5">
          {ids.map((id) => (
            <MarginRow key={id} id={id} />
          ))}
        </ul>
      )}
    </article>
  );
}

function BuyingPower({ freeCash }: { freeCash: string | undefined }) {
  const power = freeCash !== undefined ? Number(freeCash) * MAX_LEVERAGE : null;
  return (
    <div className="mt-3 space-y-1 font-mono text-xs text-muted">
      <div className="flex justify-between">
        <span>Buying power</span>
        <span className="text-fg-strong">
          {power !== null ? formatUsd(power) : "—"}
        </span>
      </div>
      <p className="leading-relaxed">
        The most notional you could open right now at {MAX_LEVERAGE}× — no open positions
        to watch.
      </p>
    </div>
  );
}

function MarginRow({ id }: { id: string }) {
  const p = usePosition(id);
  if (!p) return null;
  const pct = distanceToLiqPct(p.mark_price, p.liquidation_price);
  const danger = pct !== null && pct < 10;
  const fill =
    pct === null ? 0 : Math.max(4, Math.min(100, (pct / FULL_BAR_AT_PCT) * 100));
  return (
    <li className="font-mono text-[0.6875rem]">
      <div className="flex justify-between">
        <span className="text-fg">
          {p.pair.replace("/USD", "")} {p.side} {p.leverage}×
        </span>
        <span className={danger ? "text-down" : "text-muted"}>
          {pct === null ? "—" : `${pct.toFixed(1)}% to liq`}
        </span>
      </div>
      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className={danger ? "h-full bg-down" : "h-full bg-accent"}
          style={{ width: `${fill}%` }}
        />
      </div>
    </li>
  );
}
