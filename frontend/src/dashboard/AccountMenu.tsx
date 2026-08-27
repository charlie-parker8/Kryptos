import { useState } from "react";

import { logout } from "@/core/auth/api";
import { useSession } from "@/core/auth/useSession";
import { IS_MOCK_MODE } from "@/core/realtime/mode";

/** Session email + sign-out, in the top bar. Hidden in mock mode (no real session). */
export function AccountMenu() {
  const { user } = useSession();
  const [signingOut, setSigningOut] = useState(false);

  if (IS_MOCK_MODE) {
    return (
      <span className="rounded-control border border-border px-2 py-0.5 text-[0.6875rem] uppercase tracking-wide text-muted">
        mock
      </span>
    );
  }

  if (!user) return null;

  return (
    <div className="flex items-center gap-2">
      <span
        className="hidden max-w-[12rem] truncate font-mono text-xs text-muted md:inline"
        title={user.email}
      >
        {user.email}
      </span>
      <button
        type="button"
        onClick={() => {
          setSigningOut(true);
          void logout();
        }}
        disabled={signingOut}
        className="rounded-control border border-border px-2 py-1 text-xs text-muted transition-colors hover:border-accent hover:text-fg-strong disabled:opacity-50"
      >
        {signingOut ? "…" : "Sign out"}
      </button>
    </div>
  );
}
