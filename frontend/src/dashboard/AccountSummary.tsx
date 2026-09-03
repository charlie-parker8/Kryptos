import { formatSignedUsd, formatUsd } from "@/core/lib/money";
import { Delta } from "@/core/primitives/Delta";
import { Skeleton } from "@/core/primitives/Skeleton";
import { useDashboardData } from "@/core/useDashboardData";

const RAIL_ROWS = ["Equity", "Free cash", "Unrealised P/L", "vs start"];

/** Always-visible account state in the rail — equity, free cash, and P/L against the start. */
export function AccountSummary() {
  const { equity, freeCash, unrealizedPnl, pnlVsStart } = useDashboardData();
  if (equity === undefined) return <AccountSummarySkeleton />;

  return (
    <dl className="hidden border-t border-border px-3 py-3 font-mono text-xs lg:block">
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">Equity</dt>
        <dd className="text-fg-strong tnum">{formatUsd(equity)}</dd>
      </div>
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">Free cash</dt>
        <dd className="text-fg tnum">
          {freeCash !== undefined ? formatUsd(freeCash) : "—"}
        </dd>
      </div>
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">Unrealised P/L</dt>
        <dd
          className={
            unrealizedPnl !== undefined && Number(unrealizedPnl) < 0
              ? "text-down tnum"
              : unrealizedPnl !== undefined && Number(unrealizedPnl) > 0
                ? "text-up tnum"
                : "text-muted tnum"
          }
        >
          {unrealizedPnl !== undefined
            ? formatSignedUsd(unrealizedPnl)
            : formatSignedUsd(0)}
        </dd>
      </div>
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">vs start</dt>
        <dd>
          {pnlVsStart ? (
            <Delta abs={pnlVsStart.abs} glyphSize={7} className="text-xs" />
          ) : (
            <span className="text-muted">{formatSignedUsd(0)}</span>
          )}
        </dd>
      </div>
    </dl>
  );
}

function AccountSummarySkeleton() {
  return (
    <dl className="hidden border-t border-border px-3 py-3 font-mono text-xs lg:block">
      {RAIL_ROWS.map((label) => (
        <div key={label} className="flex items-baseline justify-between py-1">
          <dt className="text-muted">{label}</dt>
          <dd>
            <Skeleton className="h-3 w-14" />
          </dd>
        </div>
      ))}
    </dl>
  );
}
