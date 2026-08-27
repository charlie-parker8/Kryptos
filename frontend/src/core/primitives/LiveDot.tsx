/** Connection indicator. Pulses while live; steady ring under reduced motion. */

import { clsx } from "clsx";

import { useReducedMotion } from "@/core/lib/reducedMotion";

interface LiveDotProps {
  connected: boolean;
  label?: string;
  className?: string;
}

export function LiveDot({ connected, label, className }: LiveDotProps) {
  const reduced = useReducedMotion();
  const text = label ?? (connected ? "Live" : "Connecting");
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-2 text-[0.75rem] font-medium uppercase tracking-wide",
        connected ? "text-muted" : "text-down",
        className,
      )}
    >
      <span className="relative flex size-2">
        {connected && !reduced ? (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60" />
        ) : null}
        <span
          className={clsx(
            "relative inline-flex size-2 rounded-full",
            connected ? "bg-accent" : "border border-down bg-transparent",
          )}
        />
      </span>
      {text}
    </span>
  );
}
