import { memo } from "react";

import { formatUsd, pctChange } from "@/core/lib/money";
import { dirOf } from "@/core/lib/direction";
import { AnimatedNumber } from "@/core/primitives/AnimatedNumber";
import { DirGlyph } from "@/core/primitives/DirGlyph";
import { Marquee } from "@/core/primitives/Marquee";
import { PAIRS, type Pair } from "@/core/realtime/types";
import { useSessionAnchor, useTick } from "@/core/state/selectors";

export function TapeTicker() {
  return (
    <div className="tape flex h-9 items-center px-3">
      <Marquee durationSec={34} gap="3rem" className="flex-1">
        {PAIRS.map((pair) => (
          <TapeItem key={pair} pair={pair} />
        ))}
      </Marquee>
    </div>
  );
}

const TapeItem = memo(function TapeItem({ pair }: { pair: Pair }) {
  const tick = useTick(pair);
  const anchor = useSessionAnchor(pair);
  const change = tick && anchor ? pctChange(anchor, tick.last) : 0;
  const dir = dirOf(change);
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span className="text-muted">{pair}</span>
      {tick ? (
        <AnimatedNumber
          value={tick.last}
          format={(n) => formatUsd(n)}
          className="text-fg-strong"
        />
      ) : (
        <span className="text-muted">—</span>
      )}
      <span
        className={
          dir === "up" ? "text-up" : dir === "down" ? "text-down" : "text-muted"
        }
      >
        <DirGlyph dir={dir} size={7} className="mr-1" />
        {change >= 0 ? "+" : "−"}
        {Math.abs(change).toFixed(2)}%
      </span>
    </span>
  );
});
