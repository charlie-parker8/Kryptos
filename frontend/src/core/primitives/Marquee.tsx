/**
 * Horizontal auto-scroll for the price ticker. Renders enough identical copies of its
 * content to always span at least twice the container width, then slides the track left
 * by exactly one copy and loops — so items stream in from the right with no gap and no
 * visible reset, even when the content (three pairs) is far narrower than the viewport.
 * Pauses on hover, and — under reduced motion — becomes a plain scrollable row with no
 * movement.
 */

import {
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { clsx } from "clsx";

import { useReducedMotion } from "@/core/lib/reducedMotion";

interface MarqueeProps {
  children: ReactNode;
  /** seconds to traverse one copy of the content; lower = faster */
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
  const containerRef = useRef<HTMLDivElement>(null);
  const groupRef = useRef<HTMLDivElement>(null);
  const [copies, setCopies] = useState(2);

  useLayoutEffect(() => {
    if (reduced) return;
    const container = containerRef.current;
    const group = groupRef.current;
    if (!container || !group) return;

    const measure = () => {
      const groupWidth = group.scrollWidth;
      const containerWidth = container.clientWidth;
      if (groupWidth > 0 && containerWidth > 0) {
        // Track must be >= 2x the viewport for the one-copy-wide loop to stay seamless.
        setCopies(Math.max(2, Math.ceil((containerWidth * 2) / groupWidth)));
      }
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    observer.observe(group);
    return () => observer.disconnect();
  }, [reduced]);

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
    <div ref={containerRef} className={clsx("k-marquee", className)}>
      <div
        className="k-marquee-track"
        style={
          {
            ["--k-marquee-duration" as string]: `${durationSec}s`,
            ["--k-marquee-copies" as string]: String(copies),
          } as CSSProperties
        }
      >
        {Array.from({ length: copies }, (_, i) => (
          <div
            key={i}
            ref={i === 0 ? groupRef : undefined}
            className="k-marquee-group"
            style={groupStyle}
            aria-hidden={i === 0 ? undefined : "true"}
          >
            {children}
          </div>
        ))}
      </div>
    </div>
  );
}
