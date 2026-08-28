import { OpenPositions } from "@/dashboard/OpenPositions";
import { PriceChart } from "./chart/PriceChart";
import { PositionBlotter } from "./PositionBlotter";
import { PositionTicket } from "./PositionTicket";

export function TradeScreen() {
  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <header className="border-b border-border pb-6">
        <h1 className="text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
          Trade
        </h1>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Isolated-margin long/short against live Kraken prices
        </p>
      </header>

      <PriceChart />

      <div className="grid gap-8 lg:grid-cols-[20rem_1fr]">
        <div>
          <PositionTicket />
        </div>
        <div className="space-y-8">
          <OpenPositions />
          <PositionBlotter />
        </div>
      </div>
    </div>
  );
}
