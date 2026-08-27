/**
 * Route gate for the authenticated app. Unauthenticated visitors are sent to `/login` with
 * the attempted location remembered, so they land back where they meant to go. `?mock` /
 * `?frozen` bypass the gate entirely (offline dev + screenshots).
 */

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "@/core/auth/useSession";
import { IS_MOCK_MODE } from "@/core/realtime/mode";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useSession();
  const location = useLocation();

  if (IS_MOCK_MODE) return <>{children}</>;

  if (isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-bg text-muted">
        <span className="font-mono text-sm tracking-wide">Loading…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
