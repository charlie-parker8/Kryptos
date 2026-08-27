import { ASSET_OF } from "@/core/lib/format";
import { formatQty, formatUsd } from "@/core/lib/money";
import type { Order } from "@/core/api/types";
import { useOrders } from "@/core/hooks/useOrders";
import type { Pair } from "@/core/realtime/types";

const REJECTION_SHORT: Record<string, string> = {
  insufficient_funds: "no cash",
  insufficient_holdings: "no holdings",
  stale_price: "stale price",
  pair_not_tradable: "not tradable",
};

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour12: false });
}

export function OrderBlotter() {
  const { orders, isLoading, error } = useOrders();

  return (
    <section>
      <h2 className="mb-2 text-[0.6875rem] font-medium uppercase tracking-[0.12em] text-muted">
        Recent orders
      </h2>
      <div className="overflow-x-auto border border-border">
        <table className="ledger w-full min-w-[36rem] text-sm">
          <thead>
            <tr>
              <th className="text-left">Time</th>
              <th className="text-left">Order</th>
              <th className="text-right">Quantity</th>
              <th className="text-right">Price</th>
              <th className="text-right">Status</th>
            </tr>
          </thead>
          <tbody>
            {error ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-down">
                  Couldn't load your orders.
                </td>
              </tr>
            ) : isLoading ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-muted">
                  Loading…
                </td>
              </tr>
            ) : !orders || orders.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-muted">
                  No orders yet — your fills and rejections show up here.
                </td>
              </tr>
            ) : (
              orders.map((order) => <BlotterRow key={order.id} order={order} />)
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BlotterRow({ order }: { order: Order }) {
  const asset = ASSET_OF[order.symbol as Pair] ?? order.symbol.replace("/USD", "");
  return (
    <tr className="cv-row">
      <td className="text-left font-mono text-xs text-muted">
        {time(order.created_at)}
      </td>
      <td className="text-left">
        <span
          className={
            order.side === "buy"
              ? "font-medium uppercase text-up"
              : "font-medium uppercase text-down"
          }
        >
          {order.side}
        </span>{" "}
        <span className="font-mono text-fg-strong">{asset}</span>
      </td>
      <td className="text-right font-mono">{formatQty(order.quantity, 10)}</td>
      <td className="text-right font-mono">
        {order.execution_price ? formatUsd(order.execution_price) : "—"}
      </td>
      <td className="text-right">
        {order.status === "filled" ? (
          <span className="font-mono text-xs uppercase text-fg-strong">
            filled
          </span>
        ) : (
          <span
            className="font-mono text-xs uppercase text-muted"
            title={order.rejection_reason ?? undefined}
          >
            rejected
            {order.rejection_reason
              ? ` · ${REJECTION_SHORT[order.rejection_reason] ?? ""}`
              : ""}
          </span>
        )}
      </td>
    </tr>
  );
}
