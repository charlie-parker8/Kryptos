import { formatSignedUsd, formatUsd } from "@/core/lib/money";
import { Delta } from "@/core/primitives/Delta";
import { useDashboardData } from "@/core/useDashboardData";

/** Always-visible account state in the rail — net worth, cash, and P/L against the start. */
export function AccountSummary() {
  const { netWorth, cash, pnlVsStart } = useDashboardData();
  if (netWorth === undefined) return null;

  return (
    <dl className="hidden border-t border-border px-3 py-3 font-mono text-xs lg:block">
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">Net worth</dt>
        <dd className="text-fg-strong tnum">{formatUsd(netWorth)}</dd>
      </div>
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">Cash</dt>
        <dd className="text-fg tnum">
          {cash !== undefined ? formatUsd(cash) : "—"}
        </dd>
      </div>
      <div className="flex items-baseline justify-between py-1">
        <dt className="text-muted">P/L</dt>
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
