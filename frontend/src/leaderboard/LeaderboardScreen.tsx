import { formatUsd } from "@/core/lib/money";
import { ComingSoon } from "@/core/primitives/ComingSoon";
import { MOCK_STANDINGS, type Standing } from "./placeholderData";

export function LeaderboardScreen() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="border-b border-border pb-6">
        <div className="flex items-baseline justify-between">
          <h1 className="text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
            Leaderboard
          </h1>
          <ComingSoon />
        </div>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Ranked by net worth, updated as the market moves. The live standings
          service isn't wired up yet — the figures below are illustrative so you
          can see the shape of it.
        </p>
      </header>

      <div className="overflow-x-auto border border-border">
        <table className="ledger w-full min-w-[28rem] text-sm">
          <thead>
            <tr>
              <th className="text-left">#</th>
              <th className="text-left">Trader</th>
              <th className="text-right">Net worth</th>
              <th className="text-right">Move</th>
            </tr>
          </thead>
          <tbody className="opacity-70">
            {MOCK_STANDINGS.map((row) => (
              <StandingRow key={row.rank} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StandingRow({ row }: { row: Standing }) {
  const move =
    row.move > 0 ? `▲ ${row.move}` : row.move < 0 ? `▼ ${-row.move}` : "—";
  return (
    <tr className={row.isYou ? "text-accent" : undefined}>
      <td className="text-left font-mono text-muted">{row.rank}</td>
      <td className="text-left font-mono">
        {row.handle}
        {row.isYou ? (
          <span className="ml-2 text-[0.6875rem] uppercase tracking-wide">
            you
          </span>
        ) : null}
      </td>
      <td className="text-right font-mono text-fg-strong">
        {formatUsd(row.netWorth)}
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
