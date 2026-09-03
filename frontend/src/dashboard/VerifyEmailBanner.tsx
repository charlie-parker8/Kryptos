import { useState } from "react";

import { ApiError } from "@/core/api/client";
import { requestVerificationEmail } from "@/core/auth/api";
import { useSession } from "@/core/auth/useSession";

export function VerifyEmailBanner() {
  const { user } = useSession();
  const [sent, setSent] = useState(false);
  const [cooldown, setCooldown] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user || user.email_verified) return null;

  async function resend() {
    if (cooldown) return;
    setError(null);
    setCooldown(true);
    try {
      await requestVerificationEmail();
      setSent(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many requests — wait a bit."
          : "Couldn't send. Try again shortly.",
      );
    } finally {
      window.setTimeout(() => setCooldown(false), 60_000);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-accent/40 bg-accent/10 px-4 py-2 text-xs text-fg">
      <span>
        Verify your email to open positions and join the leaderboard.
        {sent ? (
          <span className="ml-2 text-muted">Sent — check your inbox.</span>
        ) : null}
        {error ? <span className="ml-2 text-down">{error}</span> : null}
      </span>
      <button
        type="button"
        onClick={() => void resend()}
        disabled={cooldown}
        className="shrink-0 font-medium text-accent hover:underline disabled:opacity-50"
      >
        Resend email
      </button>
    </div>
  );
}
