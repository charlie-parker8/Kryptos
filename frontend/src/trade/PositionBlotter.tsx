import type { Position } from "@/core/api/types";
import { usePositions } from "@/core/hooks/usePositions";
import { formatSignedUsd, formatUsd } from "@/core/lib/money";
import { SkeletonRows } from "@/core/primitives/Skeleton";

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour12: false });
}

const STATUS_LABEL: Record<Position["status"], string> = {
  open: "open",
  closed: "closed",
  liquidated: "liquidated",
};

export function PositionBlotter() {
  const { positions, isLoading, error } = usePositions();

  return (
    <section>
      <h2 className="mb-2 text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
        Position history
      </h2>
      <div className="overflow-x-auto border border-border">
        <table className="ledger w-full min-w-[40rem] text-sm">
          <thead>
            <tr>
              <th className="text-left">Opened</th>
              <th className="text-left">Position</th>
              <th className="text-right">Entry</th>
              <th className="text-right">Close</th>
              <th className="text-right">Realized P/L</th>
              <th className="text-right">Status</th>
            </tr>
          </thead>
          <tbody>
            {error ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-down">
                  Couldn't load your positions.
                </td>
              </tr>
            ) : isLoading ? (
              <SkeletonRows cols={6} rows={5} />
            ) : !positions || positions.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-muted">
                  No positions yet — your opens, closes and liquidations show up here.
                </td>
              </tr>
            ) : (
              positions.map((p) => <BlotterRow key={p.id} position={p} />)
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BlotterRow({ position }: { position: Position }) {
  const asset = position.pair.replace("/USD", "");
  const pnl = position.realized_pnl === null ? null : Number(position.realized_pnl);
  return (
    <tr className="cv-row">
      <td className="text-left font-mono text-xs text-muted">
        {time(position.opened_at)}
      </td>
      <td className="text-left">
        <span
          className={
            position.side === "long"
              ? "font-medium uppercase text-up"
              : "font-medium uppercase text-down"
          }
        >
          {position.side}
        </span>{" "}
        <span className="font-mono text-fg-strong">
          {position.leverage}× {asset}
        </span>
      </td>
      <td className="text-right font-mono">{formatUsd(position.entry_price)}</td>
      <td className="text-right font-mono">
        {position.close_price ? formatUsd(position.close_price) : "—"}
      </td>
      <td
        className={
          pnl === null
            ? "text-right font-mono text-muted"
            : pnl >= 0
              ? "text-right font-mono text-up"
              : "text-right font-mono text-down"
        }
      >
        {pnl === null ? "—" : formatSignedUsd(pnl)}
      </td>
      <td className="text-right">
        <span
          className={
            position.status === "liquidated"
              ? "font-mono text-xs uppercase text-down"
              : "font-mono text-xs uppercase text-muted"
          }
          title={position.close_reason ?? undefined}
        >
          {STATUS_LABEL[position.status]}
        </span>
      </td>
    </tr>
  );
}
