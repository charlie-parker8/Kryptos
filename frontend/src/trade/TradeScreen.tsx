import { PriceChart } from "./chart/PriceChart";
import { OrderBlotter } from "./OrderBlotter";
import { OrderTicket } from "./OrderTicket";

export function TradeScreen() {
  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <header className="border-b border-border pb-6">
        <h1 className="text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
          Trade
        </h1>
        <p className="mt-2 max-w-prose text-sm text-muted">
          Market orders only. Buys fill at the ask, sells at the bid, both at the
          price the server sees when it executes — never the number on screen.
        </p>
      </header>

      <PriceChart />

      <div className="grid gap-8 lg:grid-cols-[20rem_1fr]">
        <div>
          <OrderTicket />
        </div>
        <OrderBlotter />
      </div>
    </div>
  );
}
