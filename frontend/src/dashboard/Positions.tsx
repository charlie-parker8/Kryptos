import { memo } from "react";

import { ASSET_NAME, PAIR_OF, PAIR_PRECISION } from "@/core/lib/format";
import {
  formatQty,
  formatSignedUsd,
  formatUsd,
  unrealizedPnl,
} from "@/core/lib/money";
import { dirOf } from "@/core/lib/direction";
import { AnimatedNumber } from "@/core/primitives/AnimatedNumber";
import { DirGlyph } from "@/core/primitives/DirGlyph";
import { StaleBadge } from "@/core/primitives/StaleBadge";
import type { Asset } from "@/core/realtime/types";
import { useCash, useHolding, useHoldingSymbols } from "@/core/state/selectors";

export function Positions() {
  const symbols = useHoldingSymbols();
  const cash = useCash();

  return (
    <div className="overflow-x-auto">
      <table className="ledger w-full min-w-[44rem] text-sm">
        <thead>
          <tr>
            <th className="text-left">Symbol</th>
            <th className="text-right">Quantity</th>
            <th className="text-right">Avg cost</th>
            <th className="text-right">Last</th>
            <th className="text-right">Market value</th>
            <th className="text-right">Unrealised P/L</th>
          </tr>
        </thead>
        <tbody>
          {symbols.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-8 text-center text-muted">
                No positions yet — place your first trade.
              </td>
            </tr>
          ) : (
            symbols.map((symbol) => (
              <PositionRow key={symbol} symbol={symbol} />
            ))
          )}
          {cash !== undefined ? (
            <tr>
              <td className="text-left font-medium text-fg-strong">Cash</td>
              <td />
              <td />
              <td />
              <td className="text-right font-mono text-fg-strong tnum">
                {formatUsd(cash)}
              </td>
              <td />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

const PositionRow = memo(function PositionRow({ symbol }: { symbol: Asset }) {
  const holding = useHolding(symbol);
  if (!holding) return null;

  const empty = Number(holding.quantity) === 0;
  const precision = PAIR_PRECISION[PAIR_OF[symbol]];
  const pnl = empty
    ? null
    : unrealizedPnl(
        holding.average_cost,
        holding.quantity,
        holding.market_value,
      );
  const pnlDir = pnl ? dirOf(pnl.abs) : "flat";

  return (
    <tr className="cv-row">
      <td className="text-left">
        <span className="font-mono text-fg-strong">{symbol}</span>
        <span className="ml-2 text-[0.6875rem] uppercase tracking-wide text-muted">
          {ASSET_NAME[symbol]}
        </span>
      </td>
      <td className="text-right font-mono">
        {empty ? (
          <span className="text-muted">—</span>
        ) : (
          formatQty(holding.quantity, precision)
        )}
      </td>
      <td className="text-right font-mono">
        {empty ? (
          <span className="text-muted">—</span>
        ) : (
          formatUsd(holding.average_cost)
        )}
      </td>
      <td className="text-right font-mono">
        <span className="inline-flex items-center justify-end gap-2">
          {holding.stale ? <StaleBadge /> : null}
          {holding.current_price !== null ? (
            <AnimatedNumber
              value={holding.current_price}
              format={(n) => formatUsd(n)}
            />
          ) : (
            <span className="text-muted">—</span>
          )}
        </span>
      </td>
      <td className="text-right font-mono text-fg-strong">
        {empty || holding.market_value === null ? (
          <span className="text-muted">—</span>
        ) : (
          <AnimatedNumber
            value={holding.market_value}
            format={(n) => formatUsd(n)}
            flash={false}
          />
        )}
      </td>
      <td className="text-right font-mono">
        {pnl ? (
          <span
            className={
              pnlDir === "up"
                ? "text-up"
                : pnlDir === "down"
                  ? "text-down"
                  : "text-muted"
            }
          >
            <DirGlyph dir={pnlDir} size={8} className="mr-1.5" />
            {formatSignedUsd(pnl.abs)}
          </span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
    </tr>
  );
});
