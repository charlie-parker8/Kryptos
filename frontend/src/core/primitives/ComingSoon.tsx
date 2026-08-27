/** A small, honest label for the three features whose backend isn't built yet. */

import { clsx } from "clsx";

interface ComingSoonProps {
  className?: string;
  children?: React.ReactNode;
}

export function ComingSoon({ className, children }: ComingSoonProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-control border border-border bg-surface-2 px-2 py-0.5 text-[0.6875rem] font-medium uppercase tracking-wide text-muted",
        className,
      )}
    >
      {children ?? "Coming soon"}
    </span>
  );
}
