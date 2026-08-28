/**
 * Shown when a `bankruptcy_reset` message lands: account equity hit $0, the account was
 * reset to its starting balance and every open position closed. A deliberate moment, not a
 * toast — the user dismisses it explicitly. Mounted once in the shell.
 */

import { refreshAccount } from "@/core/hooks/useAccount";
import { formatUsd } from "@/core/lib/money";
import { Modal } from "@/core/primitives/Modal";
import {
  dismissBankruptcy,
  useBankruptcyStore,
} from "@/core/state/bankruptcyStore";

export function BankruptcyModal() {
  const event = useBankruptcyStore((s) => s.event);
  if (!event) return null;

  const closedLabel =
    event.closed_positions.length > 0
      ? event.closed_positions.join(", ")
      : "your positions";

  function acknowledge() {
    dismissBankruptcy();
    refreshAccount();
  }

  return (
    <Modal titleId="bankruptcy-title" onClose={acknowledge}>
      <h2
        id="bankruptcy-title"
        className="font-mono text-sm font-semibold uppercase tracking-[0.12em] text-down"
      >
        Wiped out
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-fg">
        Your account equity hit $0. The account is back to{" "}
        <span className="font-mono text-fg-strong">
          {formatUsd(event.starting_cash_balance)}
        </span>{" "}
        and {closedLabel}{" "}
        {event.closed_positions.length === 1 ? "was" : "were"} closed. Your
        position and ledger history is kept.
      </p>
      <button
        type="button"
        onClick={acknowledge}
        className="mt-5 w-full rounded-control bg-accent px-3 py-2 text-sm font-semibold text-accent-fg transition-opacity hover:opacity-90"
      >
        Back to it
      </button>
    </Modal>
  );
}
