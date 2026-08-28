import { NavLink, Outlet } from "react-router";

import { RealtimeConnector } from "@/app/RealtimeConnector";
import { LiveDot } from "@/core/primitives/LiveDot";
import { useIsConnected } from "@/core/state/selectors";
import { AccountSummary } from "./AccountSummary";
import { AccountMenu } from "./AccountMenu";
import { BankruptcyModal } from "./BankruptcyModal";
import { LiquidationToast } from "./LiquidationToast";
import { MarketLadder } from "./MarketLadder";
import { TapeTicker } from "./TapeTicker";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { label: "Dashboard", to: "/" },
  { label: "Trade", to: "/trade" },
  { label: "Leaderboard", to: "/leaderboard" },
];

export function AppShell() {
  const connected = useIsConnected();
  return (
    <div className="flex min-h-dvh flex-col bg-bg font-ui text-fg lg:h-dvh">
      <RealtimeConnector />
      <BankruptcyModal />
      <LiquidationToast />
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-6">
          <span className="font-mono text-sm font-semibold tracking-tight text-fg-strong">
            KRYPTOS<span className="text-accent">.</span>
          </span>
          <nav className="hidden items-center gap-1 text-[0.8125rem] sm:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  isActive
                    ? "rounded-control bg-surface-2 px-2.5 py-1 font-medium text-fg-strong"
                    : "px-2.5 py-1 text-muted transition-colors hover:text-fg"
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <LiveDot connected={connected} />
          <ThemeToggle />
          <AccountMenu />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex shrink-0 flex-col border-b border-border bg-surface-2/40 lg:w-64 lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <MarketLadder />
          <AccountSummary />
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <footer className="sticky bottom-0 shrink-0">
        <TapeTicker />
      </footer>
    </div>
  );
}
