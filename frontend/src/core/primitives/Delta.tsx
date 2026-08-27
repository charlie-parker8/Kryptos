/** A signed change — "▲ +$4,182.55  ·  +4.18%" — coloured up/down, with a drawn glyph. */

import { clsx } from "clsx";

import { dirOf } from "@/core/lib/direction";
import { formatPercent, formatSignedUsd } from "@/core/lib/money";
import { DirGlyph } from "./DirGlyph";

interface DeltaProps {
  /** absolute change in USD; omit to show percent only */
  abs?: number;
  /** percent change; omit to show absolute only */
  pct?: number;
  /** direction override (defaults to the sign of abs, then pct) */
  className?: string;
  glyphSize?: number;
  showGlyph?: boolean;
}

export function Delta({
  abs,
  pct,
  className,
  glyphSize = 10,
  showGlyph = true,
}: DeltaProps) {
  const basis = abs ?? pct ?? 0;
  const dir = dirOf(basis);
  return (
    <span
      className={clsx(
        "k-delta inline-flex items-center gap-1.5 tnum",
        dir === "up" && "text-up",
        dir === "down" && "text-down",
        dir === "flat" && "text-muted",
        className,
      )}
    >
      {showGlyph ? <DirGlyph dir={dir} size={glyphSize} /> : null}
      {abs !== undefined ? <span>{formatSignedUsd(abs)}</span> : null}
      {abs !== undefined && pct !== undefined ? (
        <span className="text-muted opacity-70">·</span>
      ) : null}
      {pct !== undefined ? <span>{formatPercent(pct)}</span> : null}
    </span>
  );
}
