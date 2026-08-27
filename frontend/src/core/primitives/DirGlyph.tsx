/** A crisp filled triangle for gain/loss direction — drawn, not a "▲" glyph (craft-floor). */

import { clsx } from "clsx";

import type { Dir } from "@/core/lib/direction";

interface DirGlyphProps {
  dir: Dir;
  size?: number;
  className?: string;
}

export function DirGlyph({ dir, size = 10, className }: DirGlyphProps) {
  if (dir === "flat") {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 10 10"
        aria-hidden="true"
        className={clsx("inline-block", className)}
      >
        <rect x="1" y="4.2" width="8" height="1.6" fill="currentColor" />
      </svg>
    );
  }
  const points = dir === "up" ? "5,1 9.5,9 0.5,9" : "0.5,1 9.5,1 5,9";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 10 10"
      aria-hidden="true"
      className={clsx("inline-block", className)}
    >
      <polygon points={points} fill="currentColor" />
    </svg>
  );
}
