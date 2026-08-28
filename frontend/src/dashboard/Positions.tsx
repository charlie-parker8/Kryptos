import { memo } from "react";

import { formatPercent, formatSignedUsd, formatUsd, pnlOf } from "@/core/lib/money";
import { AnimatedNumber } from "@/core/primitives/AnimatedNumber";
import { StaleBadge } from "@/core/primitives/StaleBadge";
import { useDashboardData } from "@/core/useDashboardData";
import { useOpenPositionIds, usePosition } from "@/core/state/selectors";

export function Positions() {
  const ids = useOpenPositionIds();
  const { freeCash } = useDashboardData();

  return (
    <div className="overflow-x-auto">
      <table className="ledger w-full min-w-[48rem] text-sm">
        <thead>
          <tr>
            <th className="text-left">Side</th>
            <th className="text-left">Pair</th>
            <th className="text-right">Lev</th>
            <th className="text-right">Collateral</th>
            <th className="text-right">Entry</th>
            <th className="text-right">Mark</th>
            <th className="text-right">Liq</th>
            <th className="text-right">Unrealised P/L</th>
          </tr>
        </thead>
        <tbody>
          {ids.length === 0 ? (
            <tr>
              <td colSpan={8} className="py-8 text-center text-muted">
                No open positions — open one from the Trade page.
              </td>
            </tr>
          ) : (
            ids.map((id) => <PositionRow key={id} id={id} />)
          )}
          {freeCash !== undefined ? (
            <tr>
              <td className="text-left font-medium text-fg-strong">Free cash</td>
              <td colSpan={6} />
              <td className="text-right font-mono text-fg-strong tnum">
                {formatUsd(freeCash)}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

const PositionRow = memo(function PositionRow({ id }: { id: string }) {
  const position = usePosition(id);
  if (!position) return null;

  const pnl = pnlOf(position.unrealized_pnl, position.collateral);
  const dir = pnl === null ? "flat" : pnl.abs >= 0 ? "up" : "down";

  return (
    <tr className="cv-row">
      <td className="text-left">
        <span
          className={
            position.side === "long"
              ? "font-medium uppercase text-up"
              : "font-medium uppercase text-down"
          }
        >
          {position.side}
        </span>
      </td>
      <td className="text-left font-mono text-fg-strong">{position.pair}</td>
      <td className="text-right font-mono">{position.leverage}×</td>
      <td className="text-right font-mono">{formatUsd(position.collateral)}</td>
      <td className="text-right font-mono">{formatUsd(position.entry_price)}</td>
      <td className="text-right font-mono">
        <span className="inline-flex items-center justify-end gap-2">
          {position.stale ? <StaleBadge /> : null}
          {position.mark_price !== null ? (
            <AnimatedNumber
              value={position.mark_price}
              format={(n) => formatUsd(n)}
            />
          ) : (
            <span className="text-muted">—</span>
          )}
        </span>
      </td>
      <td className="text-right font-mono text-down">
        {formatUsd(position.liquidation_price)}
      </td>
      <td className="text-right font-mono">
        {pnl ? (
          <span
            className={
              dir === "up"
                ? "text-up"
                : dir === "down"
                  ? "text-down"
                  : "text-muted"
            }
          >
            {formatSignedUsd(pnl.abs)}{" "}
            <span className="text-muted">({formatPercent(pnl.pct)})</span>
          </span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
    </tr>
  );
});
