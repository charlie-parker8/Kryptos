import type { ReactNode } from "react";
import { Link } from "react-router";

/**
 * Shell for the standalone legal pages (`/terms`, `/privacy`) — a single readable column
 * on the trading-desk ground, no app chrome. Prose styling is applied here with `[&_…]`
 * variants so the page bodies stay plain semantic HTML.
 */
export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-bg px-4 py-12 font-ui text-fg">
      <div className="mx-auto w-full max-w-2xl">
        <div className="mb-8 flex items-baseline justify-between">
          <Link
            to="/"
            className="font-mono text-lg font-semibold tracking-tight text-fg-strong"
          >
            KRYPTOS<span className="text-accent">.</span>
          </Link>
          <Link
            to="/"
            className="text-[0.8125rem] text-muted transition-colors hover:text-fg"
          >
            ← Back to app
          </Link>
        </div>

        <h1 className="text-xl font-semibold text-fg-strong">{title}</h1>
        <p className="mt-1 text-xs text-muted">Last updated {updated}</p>

        <div className="mt-8 space-y-4 text-sm leading-relaxed text-fg [&_a]:text-accent [&_a:hover]:underline [&_h2]:mt-8 [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-[0.08em] [&_h2]:text-fg-strong [&_li]:ml-1 [&_p]:text-muted [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_ul]:text-muted">
          {children}
        </div>

        <p className="mt-12 border-t border-border pt-6 text-xs text-muted">
          Kryptos is a paper-trading game. Real prices, fake money, no real trades.
        </p>
      </div>
    </div>
  );
}
