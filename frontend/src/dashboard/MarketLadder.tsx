import { memo } from "react";

import { ASSET_NAME, ASSET_OF, formatRelative } from "@/core/lib/format";
import { formatUsd, pctChange } from "@/core/lib/money";
import { isStale } from "@/core/lib/staleness";
import { useWallClock } from "@/core/hooks/useWallClock";
import { AnimatedNumber } from "@/core/primitives/AnimatedNumber";
import { Delta } from "@/core/primitives/Delta";
import { StaleBadge } from "@/core/primitives/StaleBadge";
import { REFERENCE_PRICE } from "@/core/realtime/mockSource";
import { PAIRS, type Pair } from "@/core/realtime/types";
import { useTick } from "@/core/state/selectors";

export function MarketLadder() {
  return (
    <div className="border-b border-border lg:border-b-0">
      <p className="px-3 pt-3 pb-2 text-[0.6875rem] font-medium uppercase tracking-[0.08em] text-muted">
        Markets
      </p>
      <div className="flex overflow-x-auto lg:block">
        {PAIRS.map((pair) => (
          <LadderRow key={pair} pair={pair} />
        ))}
      </div>
    </div>
  );
}

const LadderRow = memo(function LadderRow({ pair }: { pair: Pair }) {
  const tick = useTick(pair);
  const now = useWallClock(1000);
  const asset = ASSET_OF[pair];
  const stale = tick ? isStale(tick.as_of, now) : false;
  const change = tick ? pctChange(REFERENCE_PRICE[pair], tick.last) : 0;

  return (
    <div className="ladder-row min-w-[13rem] shrink-0 border-r border-border px-3 py-2.5 lg:min-w-0 lg:border-r-0">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[0.8125rem] text-fg-strong">
          {pair}
        </span>
        <span className="text-[0.6875rem] uppercase tracking-wide text-muted">
          {ASSET_NAME[asset]}
        </span>
      </div>
      <div className="mt-1 flex items-end justify-between gap-2">
        {tick ? (
          <AnimatedNumber
            className="font-mono text-xl text-fg-strong"
            value={tick.last}
            format={(n) => formatUsd(n)}
          />
        ) : (
          <span className="font-mono text-xl text-muted">—</span>
        )}
        {tick ? <Delta pct={change} glyphSize={8} className="text-xs" /> : null}
      </div>
      <div className="mt-1 flex items-center justify-between text-[0.6875rem] text-muted">
        <span className="font-mono">
          {tick
            ? `${Number(tick.bid).toFixed(2)} × ${Number(tick.ask).toFixed(2)}`
            : "—"}
        </span>
        {stale && tick ? (
          <StaleBadge since={tick.as_of} now={now} />
        ) : (
          <span className="tabular-nums">
            {tick ? formatRelative(tick.as_of, now) : ""}
          </span>
        )}
      </div>
    </div>
  );
});
