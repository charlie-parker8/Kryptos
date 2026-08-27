/**
 * The current login session, from `GET /auth/me`. A 401 is not an error here — it just
 * means "logged out", surfaced as `user === null`. Everything auth-gated (the route guard,
 * the shell's account menu, the dashboard's starting-cash math) reads this.
 */

import useSWR from "swr";

import { ApiError, apiGet } from "@/core/api/client";
import type { SessionUser } from "@/core/api/types";

export const SESSION_KEY = "/auth/me";

async function fetchSession(): Promise<SessionUser | null> {
  try {
    return await apiGet<SessionUser>(SESSION_KEY);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export interface Session {
  user: SessionUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export function useSession(): Session {
  const { data, isLoading } = useSWR<SessionUser | null>(
    SESSION_KEY,
    fetchSession,
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    },
  );

  return {
    user: data ?? null,
    isLoading: isLoading && data === undefined,
    isAuthenticated: !!data,
  };
}
