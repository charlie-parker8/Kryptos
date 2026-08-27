/**
 * Horizontal auto-scroll for the price ticker. Duplicates its content so the loop is
 * seamless, pauses on hover, and — under reduced motion — becomes a plain scrollable row
 * with no movement.
 */

import type { CSSProperties, ReactNode } from "react";
import { clsx } from "clsx";

import { useReducedMotion } from "@/core/lib/reducedMotion";

interface MarqueeProps {
  children: ReactNode;
  /** seconds for one full loop; lower = faster */
  durationSec?: number;
  /** space between repeated items */
  gap?: string;
  className?: string;
}

export function Marquee({
  children,
  durationSec = 42,
  gap = "2.5rem",
  className,
}: MarqueeProps) {
  const reduced = useReducedMotion();

  if (reduced) {
    return (
      <div
        className={clsx("flex items-center overflow-x-auto", className)}
        style={{ gap, columnGap: gap }}
      >
        {children}
      </div>
    );
  }

  const groupStyle: CSSProperties = { columnGap: gap, paddingInlineEnd: gap };
  return (
    <div className={clsx("k-marquee", className)}>
      <div
        className="k-marquee-track"
        style={
          {
            ["--k-marquee-duration" as string]: `${durationSec}s`,
          } as CSSProperties
        }
      >
        <div className="k-marquee-group" style={groupStyle}>
          {children}
        </div>
        <div className="k-marquee-group" style={groupStyle} aria-hidden="true">
          {children}
        </div>
      </div>
    </div>
  );
}
