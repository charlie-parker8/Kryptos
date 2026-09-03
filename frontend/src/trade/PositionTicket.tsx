import { type FormEvent, useRef, useState } from "react";

import { ApiError, apiPost } from "@/core/api/client";
import type { Position } from "@/core/api/types";
import { useSession } from "@/core/auth/useSession";
import { refreshAccount } from "@/core/hooks/useAccount";
import { refreshPositions } from "@/core/hooks/usePositions";
import { ASSET_NAME, ASSET_OF } from "@/core/lib/format";
import {
  DECIMAL_RE,
  formatUsd,
  notionalOf,
  previewLiquidationPrice,
  sizeOf,
} from "@/core/lib/money";
import { isStale } from "@/core/lib/staleness";
import { StaleBadge } from "@/core/primitives/StaleBadge";
import {
  LEVERAGE_PRESETS,
  type Leverage,
  MIN_COLLATERAL,
  PAIRS,
  type Pair,
  type PositionSide,
} from "@/core/realtime/types";
import {
  setChartPair,
  useChartSettingsStore,
} from "@/core/state/chartSettingsStore";
import { useFreeCash, usePositionOnPair, useTick } from "@/core/state/selectors";

type Result =
  | { kind: "opened"; position: Position }
  | { kind: "rejected"; reason: string }
  | { kind: "unavailable" }
  | { kind: "error"; message: string };

function validCollateral(raw: string): boolean {
  if (!DECIMAL_RE.test(raw)) return false;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < MIN_COLLATERAL) return false;
  return (raw.split(".")[1]?.length ?? 0) <= 2;
}

export function PositionTicket() {
  // Pair is shared with the chart (and persisted) so the two panels stay in lock-step.
  const pair = useChartSettingsStore((s) => s.pair);
  const [side, setSide] = useState<PositionSide>("long");
  const [leverage, setLeverage] = useState<Leverage>(LEVERAGE_PRESETS[0]);
  const [collateral, setCollateral] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // One idempotency key per open intent: minted on submit, kept across a 503 retry,
  // cleared once the request resolves or the ticket changes.
  const idempotencyKey = useRef<string | null>(null);

  const { user } = useSession();
  const emailUnverified = !!user && !user.email_verified; // mock mode has no user -> false

  const tick = useTick(pair);
  const freeCash = useFreeCash();
  const asset = ASSET_OF[pair];
  const existing = usePositionOnPair(pair);

  const mark = tick?.last;
  const stale = tick ? isStale(tick.as_of) : false;

  const notional =
    validCollateral(collateral) ? notionalOf(collateral, leverage) : null;
  const size = notional && mark ? sizeOf(notional, mark) : null;
  const liq = mark ? previewLiquidationPrice(side, mark, leverage) : null;

  const overspend =
    validCollateral(collateral) && freeCash !== undefined
      ? Number(collateral) > Number(freeCash)
      : false;
  const blocked =
    !validCollateral(collateral) ||
    overspend ||
    existing !== undefined ||
    emailUnverified;

  function resetIntent() {
    idempotencyKey.current = null;
    setResult(null);
  }

  async function submit() {
    if (blocked) return;
    const key = (idempotencyKey.current ??= crypto.randomUUID());
    setSubmitting(true);
    setResult(null);
    try {
      const position = await apiPost<Position>(
        "/positions",
        { pair, side, collateral, leverage },
        { "Idempotency-Key": key },
      );
      idempotencyKey.current = null;
      setResult({ kind: "opened", position });
      setCollateral("");
      refreshPositions();
      refreshAccount();
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setResult({ kind: "unavailable" }); // keep the key — Retry reuses it
      } else if (err instanceof ApiError && err.status === 401) {
        setResult({ kind: "error", message: "Your session expired. Sign in again." });
      } else if (err instanceof ApiError && isRejection(err)) {
        idempotencyKey.current = null;
        setResult({
          kind: "rejected",
          reason: err.detail ?? "That order was rejected.",
        });
      } else {
        idempotencyKey.current = null;
        setResult({ kind: "error", message: "Couldn't open the position. Try again." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit();
  }

  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4 border border-border bg-surface p-4"
    >
      <div className="grid grid-cols-2 gap-2">
        {(["long", "short"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setSide(s);
              resetIntent();
            }}
            className={
              side === s
                ? s === "long"
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
            setChartPair(e.target.value as Pair);
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

      <div>
        <span className="mb-1 block text-[0.6875rem] font-medium uppercase tracking-[0.1em] text-muted">
          Leverage
        </span>
        <div className="grid grid-cols-3 gap-2">
          {LEVERAGE_PRESETS.map((lev) => (
            <button
              key={lev}
              type="button"
              onClick={() => {
                setLeverage(lev);
                resetIntent();
              }}
              className={
                leverage === lev
                  ? "rounded-control border border-accent bg-accent/10 py-2 font-mono text-sm font-semibold text-accent"
                  : "rounded-control border border-border py-2 font-mono text-sm text-muted transition-colors hover:text-fg"
              }
            >
              {lev}×
            </button>
          ))}
        </div>
      </div>

      <label className="block">
        <span className="mb-1 block text-[0.6875rem] font-medium uppercase tracking-[0.1em] text-muted">
          Collateral (USD)
        </span>
        <input
          inputMode="decimal"
          autoComplete="off"
          placeholder="0.00"
          value={collateral}
          onChange={(e) => {
            setCollateral(e.target.value.trim());
            resetIntent();
          }}
          className="w-full rounded-control border border-border bg-bg px-3 py-2 font-mono text-sm text-fg-strong outline-none placeholder:text-muted focus:border-accent"
        />
        {freeCash !== undefined ? (
          <button
            type="button"
            onClick={() => {
              setCollateral(freeCash);
              resetIntent();
            }}
            className="mt-1 font-mono text-[0.6875rem] text-muted hover:text-accent"
          >
            Free cash {formatUsd(freeCash)} — use all
          </button>
        ) : null}
      </label>

      <dl className="space-y-1.5 border-t border-hairline pt-3 font-mono text-xs">
        <div className="flex justify-between">
          <dt className="text-muted">Mark price</dt>
          <dd className="flex items-center gap-2 text-fg-strong">
            {stale && tick ? <StaleBadge since={tick.as_of} /> : null}
            {mark ? formatUsd(mark) : "—"}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Notional</dt>
          <dd className="text-fg-strong">{notional ? formatUsd(notional) : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Position size</dt>
          <dd className="text-fg">
            {size !== null ? `${size.toPrecision(6)} ${asset}` : "—"}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Liquidation ≈</dt>
          <dd className={side === "long" ? "text-down" : "text-down"}>
            {liq !== null ? formatUsd(liq) : "—"}
          </dd>
        </div>
      </dl>

      {emailUnverified ? (
        <p className="text-xs text-down">
          Verify your email to open a position — see the banner at the top.
        </p>
      ) : existing ? (
        <p className="text-xs text-down">
          You have an open {existing.side} on {pair}. Close it before opening another.
        </p>
      ) : overspend ? (
        <p className="text-xs text-down">That's more than your free cash.</p>
      ) : null}

      <button
        type="submit"
        disabled={submitting || blocked}
        className="w-full rounded-control bg-accent px-3 py-2 text-sm font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        {submitting
          ? "Opening…"
          : `Open ${side} · ${leverage}× ${asset}`}
      </button>

      <p className="text-[0.6875rem] leading-relaxed text-muted">
        Marked at the live price. Liquidation and entry are priced by the server at
        execution — the numbers above are a preview.
      </p>

      <ResultNotice result={result} onRetry={submit} onDismiss={resetIntent} />
    </form>
  );
}

function isRejection(err: ApiError): boolean {
  return (
    err.status === 402 ||
    err.status === 403 ||
    err.status === 409 ||
    err.status === 422
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

  if (result.kind === "opened") {
    const p = result.position;
    return (
      <p
        role="status"
        className="border border-up/40 bg-up/10 px-3 py-2 text-xs text-up"
      >
        Opened {p.side} {p.leverage}× {p.pair.replace("/USD", "")} · entry{" "}
        {formatUsd(p.entry_price)} · liq {formatUsd(p.liquidation_price)}.
      </p>
    );
  }

  if (result.kind === "rejected") {
    return (
      <p
        role="status"
        className="border border-border bg-surface-2 px-3 py-2 text-xs text-fg"
      >
        <span className="font-medium text-fg-strong">Rejected.</span>{" "}
        {result.reason}
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
