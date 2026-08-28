/**
 * Live open positions — one card per position, valued off the `account_update` stream.
 * Shown on both the Trade page and the Dashboard. The Close button hits
 * `POST /positions/{id}/close`; the server prices the close, so the card just reflects
 * whatever the next `account_update` / `position_update` says.
 */

import { memo, useState } from "react";

import { ApiError, apiPost } from "@/core/api/client";
import { refreshAccount } from "@/core/hooks/useAccount";
import { refreshPositions } from "@/core/hooks/usePositions";
import { formatPercent, formatSignedUsd, formatUsd, pnlOf } from "@/core/lib/money";
import { StaleBadge } from "@/core/primitives/StaleBadge";
import { useOpenPositionIds, usePosition } from "@/core/state/selectors";

export function OpenPositions() {
  const ids = useOpenPositionIds();

  return (
    <section>
      <h2 className="mb-2 text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
        Open positions
      </h2>
      {ids.length === 0 ? (
        <p className="border border-border bg-surface px-4 py-8 text-center text-sm text-muted">
          No open positions — commit collateral in the ticket to open one.
        </p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {ids.map((id) => (
            <PositionCard key={id} id={id} />
          ))}
        </ul>
      )}
    </section>
  );
}

const PositionCard = memo(function PositionCard({ id }: { id: string }) {
  const position = usePosition(id);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!position) return null;

  const pnl = pnlOf(position.unrealized_pnl, position.collateral);
  const dir = pnl === null ? "flat" : pnl.abs >= 0 ? "up" : "down";
  const distanceToLiq =
    position.mark_price !== null
      ? (Math.abs(
          Number(position.mark_price) - Number(position.liquidation_price),
        ) /
          Number(position.mark_price)) *
        100
      : null;

  async function close() {
    setClosing(true);
    setError(null);
    try {
      await apiPost(`/positions/${id}/close`);
      refreshAccount();
      refreshPositions();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.detail ?? "Couldn't close. Try again.")
          : "Couldn't close. Try again.",
      );
      setClosing(false);
    }
  }

  return (
    <li className="border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between">
        <span
          className={
            position.side === "long"
              ? "font-mono text-sm font-semibold uppercase text-up"
              : "font-mono text-sm font-semibold uppercase text-down"
          }
        >
          {position.side} {position.leverage}×
        </span>
        <span className="font-mono text-sm text-fg-strong">{position.pair}</span>
      </div>

      <dl className="mt-3 space-y-1 font-mono text-xs">
        <Row label="Collateral" value={formatUsd(position.collateral)} />
        <Row label="Entry" value={formatUsd(position.entry_price)} />
        <Row
          label="Mark"
          value={
            <span className="inline-flex items-center gap-2">
              {position.stale ? <StaleBadge /> : null}
              {position.mark_price ? formatUsd(position.mark_price) : "—"}
            </span>
          }
        />
        <Row
          label="Liquidation"
          value={
            <span className="text-down">
              {formatUsd(position.liquidation_price)}
              {distanceToLiq !== null ? (
                <span className="ml-1 text-muted">
                  ({distanceToLiq.toFixed(1)}%)
                </span>
              ) : null}
            </span>
          }
        />
        <Row
          label="Unrealized P/L"
          value={
            pnl === null ? (
              <span className="text-muted">—</span>
            ) : (
              <span
                className={
                  dir === "up"
                    ? "text-up"
                    : dir === "down"
                      ? "text-down"
                      : "text-muted"
                }
              >
                {formatSignedUsd(pnl.abs)} ({formatPercent(pnl.pct)})
              </span>
            )
          }
        />
      </dl>

      {error ? <p className="mt-2 text-xs text-down">{error}</p> : null}

      <button
        type="button"
        onClick={close}
        disabled={closing}
        className="mt-3 w-full rounded-control border border-border py-1.5 text-xs font-medium uppercase tracking-wide text-muted transition-colors hover:border-down hover:text-down disabled:opacity-40"
      >
        {closing ? "Closing…" : "Close position"}
      </button>
    </li>
  );
});

function Row({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted">{label}</dt>
      <dd className="text-fg-strong">{value}</dd>
    </div>
  );
}
