import type { ReactNode } from "react";

/** The shell for the login / register screens — centred card on the trading-desk ground. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-bg px-4 font-ui text-fg">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-baseline gap-2">
          <span className="font-mono text-lg font-semibold tracking-tight text-fg-strong">
            KRYPTOS<span className="text-accent">.</span>
          </span>
          <span className="text-[0.6875rem] uppercase tracking-[0.14em] text-muted">
            paper trading
          </span>
        </div>
        <div className="border border-border bg-surface p-6">{children}</div>
        <p className="mt-4 text-center text-[0.6875rem] leading-relaxed text-muted">
          Fake money, real prices. No trade ever settles for real.
        </p>
      </div>
    </div>
  );
}
