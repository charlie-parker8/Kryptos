import type { LeaderboardEntry } from "@/core/api/types";
import { useLeaderboard } from "@/core/hooks/useLeaderboard";
import { formatUsd } from "@/core/lib/money";

export function LeaderboardScreen() {
  const { standings, you, isLoading, error } = useLeaderboard();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="border-b border-border pb-6">
        <h1 className="text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
          Leaderboard
        </h1>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Every account ranked by equity — free cash plus each open position's
          collateral and unrealised P&L — updated as the market moves. The move
          column is the change in rank since the last standings sweep.
        </p>
      </header>

      <div className="overflow-x-auto border border-border">
        <table className="ledger w-full min-w-[28rem] text-sm">
          <thead>
            <tr>
              <th className="text-left">#</th>
              <th className="text-left">Trader</th>
              <th className="text-right">Equity</th>
              <th className="text-right">Move</th>
            </tr>
          </thead>
          <tbody>
            {error ? (
              <tr>
                <td colSpan={4} className="py-8 text-center text-down">
                  Couldn't load the standings.
                </td>
              </tr>
            ) : isLoading || !standings ? (
              <tr>
                <td colSpan={4} className="py-8 text-center text-muted">
                  Loading…
                </td>
              </tr>
            ) : standings.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-8 text-center text-muted">
                  No standings yet — place a trade to get on the board.
                </td>
              </tr>
            ) : (
              <>
                {standings.map((row) => (
                  <StandingRow key={row.rank} row={row} />
                ))}
                {you ? (
                  <>
                    <tr>
                      <td
                        colSpan={4}
                        className="py-1 text-center text-[0.625rem] uppercase tracking-[0.16em] text-muted"
                      >
                        your position
                      </td>
                    </tr>
                    <StandingRow row={you} />
                  </>
                ) : null}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StandingRow({ row }: { row: LeaderboardEntry }) {
  const move =
    row.move > 0 ? `▲ ${row.move}` : row.move < 0 ? `▼ ${-row.move}` : "—";
  return (
    <tr className={row.is_you ? "text-accent" : undefined}>
      <td className="text-left font-mono text-muted">{row.rank}</td>
      <td className="text-left font-mono">
        {row.username}
        {row.is_you ? (
          <span className="ml-2 text-[0.6875rem] uppercase tracking-wide">
            you
          </span>
        ) : null}
      </td>
      <td
        className={
          Number(row.equity) < 0
            ? "text-right font-mono text-down tnum"
            : "text-right font-mono text-fg-strong tnum"
        }
      >
        {formatUsd(row.equity)}
      </td>
      <td
        className={
          row.move > 0
            ? "text-right font-mono text-up"
            : row.move < 0
              ? "text-right font-mono text-down"
              : "text-right font-mono text-muted"
        }
      >
        {move}
      </td>
    </tr>
  );
}
