/**
 * A number that rolls to its new value and flashes its direction — without re-rendering
 * anything. All animation state lives in refs; the rAF loop writes `textContent` directly
 * and the resting frame always shows the exact formatted value. `prefers-reduced-motion`
 * snaps to the value and keeps only the colour change.
 *
 * Style it through the `.k-animated-number` class (see styles/index.css + each skin's
 * theme.css). It sets `data-dir="up" | "down"` for ~0.7s after a change.
 */

import { useLayoutEffect, useRef } from "react";

import { prefersReducedMotion } from "@/core/lib/reducedMotion";
import { clsx } from "clsx";

interface AnimatedNumberProps {
  /** decimal string from the wire */
  value: string;
  /** wire string / tween frame number → display text */
  format: (n: number) => string;
  className?: string;
  /** count-tween length in ms; 0 disables the roll (keeps the flash) */
  duration?: number;
  /** colour-flash the direction of change (default true) */
  flash?: boolean;
}

const easeOutCubic = (t: number): number => 1 - (1 - t) ** 3;
const FLASH_MS = 700;

export function AnimatedNumber({
  value,
  format,
  className,
  duration = 460,
  flash = true,
}: AnimatedNumberProps) {
  const spanRef = useRef<HTMLSpanElement>(null);
  const displayed = useRef(Number(value));
  const raf = useRef<number | null>(null);
  const flashTimer = useRef<number | null>(null);
  const first = useRef(true);

  // Keep the latest formatter without making it an effect dependency (advanced-use-latest).
  // Layout effects run in declaration order, so this syncs before the animation effect reads it.
  const formatRef = useRef(format);
  useLayoutEffect(() => {
    formatRef.current = format;
  });

  useLayoutEffect(() => {
    const node = spanRef.current;
    if (!node) return;
    const fmt = formatRef.current;
    const target = Number(value);
    const from = displayed.current;

    if (first.current) {
      first.current = false;
      displayed.current = target;
      node.textContent = fmt(target);
      return;
    }
    if (target === from) return;

    if (flash) {
      node.dataset.dir = target > from ? "up" : "down";
      if (flashTimer.current) clearTimeout(flashTimer.current);
      flashTimer.current = window.setTimeout(() => {
        delete node.dataset.dir;
        flashTimer.current = null;
      }, FLASH_MS);
    }

    if (duration <= 0 || prefersReducedMotion()) {
      displayed.current = target;
      node.textContent = fmt(target);
      return;
    }

    const startedAt = performance.now();
    if (raf.current) cancelAnimationFrame(raf.current);
    const step = (now: number): void => {
      const t = Math.min(1, (now - startedAt) / duration);
      if (t >= 1) {
        displayed.current = target;
        node.textContent = fmt(target);
        raf.current = null;
        return;
      }
      node.textContent = fmt(from + (target - from) * easeOutCubic(t));
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  }, [value, duration, flash]);

  useLayoutEffect(
    () => () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      if (flashTimer.current) clearTimeout(flashTimer.current);
    },
    [],
  );

  return (
    <span ref={spanRef} className={clsx("k-animated-number tnum", className)} />
  );
}
