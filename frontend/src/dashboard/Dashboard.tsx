import { Link } from "react-router";

import { useLeaderboard } from "@/core/hooks/useLeaderboard";
import { formatClock } from "@/core/lib/format";
import { formatSignedUsd, formatUsd } from "@/core/lib/money";
import { Delta } from "@/core/primitives/Delta";
import { LEVERAGE_PRESETS, PAIRS } from "@/core/realtime/types";
import { useDashboardData } from "@/core/useDashboardData";
import { Positions } from "./Positions";
import { SplitFlapNumber } from "./SplitFlapNumber";

export function Dashboard() {
  const { equity, freeCash, unrealizedPnl, pnlVsStart, startingCash, asOf } =
    useDashboardData();
  const { standings } = useLeaderboard();
  const startingCashLabel = startingCash ? formatUsd(startingCash) : "—";
  const topStandings = standings?.slice(0, 4) ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <section className="border-b border-border pb-6">
        <div className="flex items-baseline justify-between">
          <h1 className="text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
            Account equity
          </h1>
          {asOf ? (
            <span className="font-mono text-[0.6875rem] text-muted">
              {formatClock(asOf)} · valued live
            </span>
          ) : null}
        </div>
        <div className="mt-3 overflow-x-auto">
          {equity ? (
            <SplitFlapNumber
              className="text-[2rem] sm:text-5xl lg:text-6xl"
              value={equity}
              format={(n) => formatUsd(n)}
            />
          ) : (
            <span className="font-mono text-5xl text-muted">—</span>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          {pnlVsStart ? (
            <span className="flex items-center gap-3">
              <Delta abs={pnlVsStart.abs} pct={pnlVsStart.pct} />
              <span className="text-muted">
                against the {startingCashLabel} you started with
              </span>
            </span>
          ) : null}
          <span className="font-mono text-xs text-muted">
            Free cash{" "}
            <span className="text-fg">
              {freeCash !== undefined ? formatUsd(freeCash) : "—"}
            </span>
          </span>
          <span className="font-mono text-xs text-muted">
            Unrealised{" "}
            <span
              className={
                unrealizedPnl !== undefined && Number(unrealizedPnl) < 0
                  ? "text-down"
                  : unrealizedPnl !== undefined && Number(unrealizedPnl) > 0
                    ? "text-up"
                    : "text-fg"
              }
            >
              {unrealizedPnl !== undefined
                ? formatSignedUsd(unrealizedPnl)
                : "—"}
            </span>
          </span>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
          Positions
        </h2>
        <Positions />
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <Link
          to="/leaderboard"
          className="border border-border p-4 transition-colors hover:border-accent"
        >
          <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
            Leaderboard
          </h3>
          {topStandings.length > 0 ? (
            <ol className="mt-3 space-y-1.5 font-mono text-xs">
              {topStandings.map((row) => (
                <li
                  key={row.rank}
                  className={`flex justify-between ${row.is_you ? "text-accent" : "text-muted"}`}
                >
                  <span>
                    {row.rank}. {row.username}
                  </span>
                  <span>{formatUsd(row.equity)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-xs text-muted">Standings load in a moment…</p>
          )}
        </Link>

        <article className="border border-border p-4">
          <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
            Reset rule
          </h3>
          <p className="mt-3 text-xs leading-relaxed text-muted">
            If account equity reaches $0, the account resets to {startingCashLabel},
            every open position closes, and history is kept.
          </p>
        </article>

        <article className="border border-border p-4">
          <h3 className="text-xs font-medium uppercase tracking-wide text-fg-strong">
            Limits
          </h3>
          <dl className="mt-3 space-y-1.5 font-mono text-xs text-muted">
            <div className="flex justify-between">
              <dt>Starting cash</dt>
              <dd className="text-fg">{startingCashLabel}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Leverage</dt>
              <dd className="text-fg">
                {LEVERAGE_PRESETS.map((l) => `${l}×`).join(" · ")}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Pairs</dt>
              <dd className="text-fg">
                {PAIRS.map((p) => p.replace("/USD", "")).join(" · ")}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Maint. margin</dt>
              <dd className="text-fg">0.5%</dd>
            </div>
          </dl>
        </article>
      </section>
    </div>
  );
}
