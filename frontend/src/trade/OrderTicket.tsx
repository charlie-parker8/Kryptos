import { type FormEvent, useRef, useState } from "react";

import { ApiError, apiPost } from "@/core/api/client";
import type { Order, OrderSide, RejectionReason } from "@/core/api/types";
import { refreshOrders } from "@/core/hooks/useOrders";
import { refreshPortfolio } from "@/core/hooks/usePortfolio";
import { ASSET_NAME, ASSET_OF } from "@/core/lib/format";
import { DECIMAL_RE, estimateNotional, formatQty, formatUsd } from "@/core/lib/money";
import { isStale } from "@/core/lib/staleness";
import { StaleBadge } from "@/core/primitives/StaleBadge";
import { PAIRS, type Pair } from "@/core/realtime/types";
import { useCash, useHolding, useTick } from "@/core/state/selectors";

type Result =
  | { kind: "filled"; order: Order }
  | { kind: "rejected"; order: Order }
  | { kind: "unavailable" }
  | { kind: "error"; message: string };

const REJECTION_COPY: Record<RejectionReason, string> = {
  insufficient_funds: "Not enough cash for that order.",
  insufficient_holdings: "You don't hold enough to sell that much.",
  stale_price: "The price went stale before this could fill. Try again in a moment.",
  pair_not_tradable: "This pair isn't tradable right now.",
};

function validQuantity(raw: string): boolean {
  if (!DECIMAL_RE.test(raw)) return false;
  if (Number(raw) <= 0) return false;
  const dp = raw.split(".")[1]?.length ?? 0;
  return dp <= 10;
}

export function OrderTicket() {
  const [pair, setPair] = useState<Pair>("BTC/USD");
  const [side, setSide] = useState<OrderSide>("buy");
  const [quantity, setQuantity] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // One idempotency key per order intent: minted on submit, kept across a 503 retry,
  // cleared once the order resolves or the ticket changes.
  const idempotencyKey = useRef<string | null>(null);

  const tick = useTick(pair);
  const cash = useCash();
  const asset = ASSET_OF[pair];
  const holding = useHolding(asset);

  const price = tick ? (side === "buy" ? tick.ask : tick.bid) : undefined;
  const stale = tick ? isStale(tick.as_of) : false;
  const estimate =
    price && validQuantity(quantity) ? estimateNotional(price, quantity) : null;

  const heldQty = holding?.quantity ?? "0";
  const overspend =
    side === "buy" && estimate !== null && cash !== undefined
      ? Number(estimate) > Number(cash)
      : false;
  const oversell =
    side === "sell" && validQuantity(quantity)
      ? Number(quantity) > Number(heldQty)
      : false;

  function resetIntent() {
    idempotencyKey.current = null;
    setResult(null);
  }

  async function submit() {
    if (!validQuantity(quantity)) return;
    const key = (idempotencyKey.current ??= crypto.randomUUID());
    setSubmitting(true);
    setResult(null);
    try {
      const order = await apiPost<Order>(
        "/orders",
        { symbol: pair, side, quantity },
        { "Idempotency-Key": key },
      );
      idempotencyKey.current = null;
      setResult(
        order.status === "filled"
          ? { kind: "filled", order }
          : { kind: "rejected", order },
      );
      refreshOrders();
      refreshPortfolio();
      if (order.status === "filled") setQuantity("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setResult({ kind: "unavailable" }); // keep the key — Retry reuses it
      } else if (err instanceof ApiError && err.status === 401) {
        setResult({ kind: "error", message: "Your session expired. Sign in again." });
      } else {
        setResult({
          kind: "error",
          message: "Couldn't place the order. Try again.",
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit();
  }

  const blocked = !validQuantity(quantity) || overspend || oversell;

  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4 border border-border bg-surface p-4"
    >
      <div className="grid grid-cols-2 gap-2">
        {(["buy", "sell"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setSide(s);
              resetIntent();
            }}
            className={
              side === s
                ? s === "buy"
                  ? "rounded-control border border-up bg-up/10 py-2 text-sm font-semibold uppercase tracking-wide text-up"
                  : "rounded-control border border-down bg-down/10 py-2 text-sm font-semibold uppercase tracking-wide text-down"
                : "rounded-control border border-border py-2 text-sm font-medium uppercase tracking-wide text-muted transition-colors hover:text-fg"
            }
          >
            {s}
          </button>
        ))}
      </div>

      <label className="block">
        <span className="mb-1 block text-[0.6875rem] font-medium uppercase tracking-[0.1em] text-muted">
          Pair
        </span>
        <select
          value={pair}
          onChange={(e) => {
            setPair(e.target.value as Pair);
            resetIntent();
          }}
          className="w-full rounded-control border border-border bg-bg px-3 py-2 font-mono text-sm text-fg-strong outline-none focus:border-accent"
        >
          {PAIRS.map((p) => (
            <option key={p} value={p}>
              {p} — {ASSET_NAME[ASSET_OF[p]]}
            </option>
          ))}
        </select>
      </label>

      <label className="block">
        <span className="mb-1 block text-[0.6875rem] font-medium uppercase tracking-[0.1em] text-muted">
          Quantity ({asset})
        </span>
        <input
          inputMode="decimal"
          autoComplete="off"
          placeholder="0.00"
          value={quantity}
          onChange={(e) => {
            setQuantity(e.target.value.trim());
            resetIntent();
          }}
          className="w-full rounded-control border border-border bg-bg px-3 py-2 font-mono text-sm text-fg-strong outline-none placeholder:text-muted focus:border-accent"
        />
        {side === "sell" ? (
          Number(heldQty) > 0 ? (
            <button
              type="button"
              onClick={() => {
                setQuantity(heldQty);
                resetIntent();
              }}
              className="mt-1 font-mono text-[0.6875rem] text-muted hover:text-accent"
            >
              Hold {formatQty(heldQty, 10)} {asset} — sell all
            </button>
          ) : (
            <p className="mt-1 font-mono text-[0.6875rem] text-muted">
              No {asset} to sell.
            </p>
          )
        ) : null}
      </label>

      <dl className="space-y-1.5 border-t border-hairline pt-3 font-mono text-xs">
        <div className="flex justify-between">
          <dt className="text-muted">
            {side === "buy" ? "Ask" : "Bid"} price
          </dt>
          <dd className="flex items-center gap-2 text-fg-strong">
            {stale && tick ? <StaleBadge since={tick.as_of} /> : null}
            {price ? formatUsd(price) : "—"}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Est. {side === "buy" ? "cost" : "proceeds"}</dt>
          <dd className="text-fg-strong">{estimate ? formatUsd(estimate) : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">
            {side === "buy" ? "Cash available" : `${asset} held`}
          </dt>
          <dd className="text-fg">
            {side === "buy"
              ? cash !== undefined
                ? formatUsd(cash)
                : "—"
              : `${formatQty(heldQty, 10)} ${asset}`}
          </dd>
        </div>
      </dl>

      {overspend ? (
        <p className="text-xs text-down">
          That's more than your cash balance.
        </p>
      ) : null}
      {oversell ? (
        <p className="text-xs text-down">
          You only hold {formatQty(heldQty, 10)} {asset}.
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting || blocked}
        className="w-full rounded-control bg-accent px-3 py-2 text-sm font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        {submitting
          ? "Placing…"
          : `${side === "buy" ? "Buy" : "Sell"} ${asset}`}
      </button>

      <p className="text-[0.6875rem] leading-relaxed text-muted">
        Market order, fills at the live {side === "buy" ? "ask" : "bid"}. The
        estimate is a preview — the server prices the fill at execution.
      </p>

      <ResultNotice result={result} onRetry={submit} onDismiss={resetIntent} />
    </form>
  );
}

function ResultNotice({
  result,
  onRetry,
  onDismiss,
}: {
  result: Result | null;
  onRetry: () => void | Promise<void>;
  onDismiss: () => void;
}) {
  if (!result) return null;

  if (result.kind === "filled") {
    const o = result.order;
    return (
      <p
        role="status"
        className="border border-up/40 bg-up/10 px-3 py-2 text-xs text-up"
      >
        {o.side === "buy" ? "Bought" : "Sold"} {formatQty(o.quantity, 10)}{" "}
        {o.symbol.replace("/USD", "")} at{" "}
        {o.execution_price ? formatUsd(o.execution_price) : "market"}.
      </p>
    );
  }

  if (result.kind === "rejected") {
    const reason = result.order.rejection_reason;
    return (
      <p
        role="status"
        className="border border-border bg-surface-2 px-3 py-2 text-xs text-fg"
      >
        <span className="font-medium text-fg-strong">Order rejected.</span>{" "}
        {reason ? REJECTION_COPY[reason] : "Try again."}
      </p>
    );
  }

  if (result.kind === "unavailable") {
    return (
      <div className="border border-border bg-surface-2 px-3 py-2 text-xs text-fg">
        <p>Market data is briefly unavailable.</p>
        <button
          type="button"
          onClick={() => void onRetry()}
          className="mt-1.5 font-medium text-accent hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="border border-down/40 bg-down/10 px-3 py-2 text-xs text-down">
      <p>{result.message}</p>
      <button
        type="button"
        onClick={onDismiss}
        className="mt-1.5 font-medium hover:underline"
      >
        Dismiss
      </button>
    </div>
  );
}
