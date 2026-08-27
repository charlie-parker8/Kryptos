import { formatClock } from "@/core/lib/format";
import { formatUsd } from "@/core/lib/money";
import { ComingSoon } from "@/core/primitives/ComingSoon";
import { Delta } from "@/core/primitives/Delta";
import { MOCK_STANDINGS } from "@/core/realtime/mockSource";
import { PAIRS } from "@/core/realtime/types";
import { useDashboardData } from "@/core/useDashboardData";
import { Positions } from "./Positions";
import { SplitFlapNumber } from "./SplitFlapNumber";

export function Dashboard() {
  const { netWorth, pnlVsStart, startingCash, asOf } = useDashboardData();

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <section className="border-b border-border pb-6">
        <div className="flex items-baseline justify-between">
          <h1 className="text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
            Net worth
          </h1>
          {asOf ? (
            <span className="font-mono text-[0.6875rem] text-muted">
              {formatClock(asOf)} · valued live
            </span>
          ) : null}
        </div>
        <div className="mt-3 overflow-x-auto">
          {netWorth ? (
            <SplitFlapNumber
              className="text-[2rem] sm:text-5xl lg:text-6xl"
              value={netWorth}
              format={(n) => formatUsd(n)}
            />
          ) : (
            <span className="font-mono text-5xl text-muted">—</span>
          )}
        </div>
        {pnlVsStart ? (
          <p className="mt-3 flex items-center gap-3 text-sm">
            <Delta abs={pnlVsStart.abs} pct={pnlVsStart.pct} />
            <span className="text-muted">
              against the {formatUsd(startingCash)} you started with
            </span>
          </p>
        ) : null}
      </section>

      <section>
        <h2 className="mb-2 text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
          Positions
        </h2>
        <Positions />
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <article className="border border-border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
              Leaderboard
            </h3>
            <ComingSoon />
          </div>
          <ol className="mt-3 space-y-1.5 font-mono text-xs">
            {MOCK_STANDINGS.slice(0, 4).map((row) => (
              <li
                key={row.rank}
                className={`flex justify-between ${"isYou" in row && row.isYou ? "text-accent" : "text-muted"}`}
              >
                <span>
                  {row.rank}. {row.handle}
                </span>
                <span>{formatUsd(row.netWorth)}</span>
              </li>
            ))}
          </ol>
        </article>

        <article className="border border-border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
              Reset rule
            </h3>
            <ComingSoon />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted">
            If net worth reaches $0, the account resets to{" "}
            {formatUsd(startingCash)} and holdings clear. Order and ledger
            history is kept.
          </p>
        </article>

        <article className="border border-border p-4">
          <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
            Limits
          </h3>
          <dl className="mt-3 space-y-1.5 font-mono text-xs text-muted">
            <div className="flex justify-between">
              <dt>Starting cash</dt>
              <dd className="text-fg">{formatUsd(startingCash)}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Pairs</dt>
              <dd className="text-fg">
                {PAIRS.map((p) => p.replace("/USD", "")).join(" · ")}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Price max age</dt>
              <dd className="text-fg">10s</dd>
            </div>
          </dl>
        </article>
      </section>
    </div>
  );
}
