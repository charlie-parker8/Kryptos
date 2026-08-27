/**
 * Auth actions. Each one hits the backend, then refreshes the SWR session cache so the
 * route guard and shell re-render against the new state. The backend sets / clears the
 * httponly `kryptos_session` cookie itself — nothing to store client-side.
 */

import { mutate } from "swr";

import { apiPost } from "@/core/api/client";
import type { SessionUser } from "@/core/api/types";
import { disconnectRealtime } from "@/core/realtime/connectRealtime";
import { resetMarket } from "@/core/state/marketStore";
import { resetPortfolio } from "@/core/state/portfolioStore";
import { SESSION_KEY } from "./useSession";

export async function login(
  email: string,
  password: string,
): Promise<SessionUser> {
  const user = await apiPost<SessionUser>("/auth/login", { email, password });
  await mutate(SESSION_KEY, user, { revalidate: false });
  return user;
}

export async function register(
  email: string,
  password: string,
): Promise<SessionUser> {
  const user = await apiPost<SessionUser>("/auth/register", { email, password });
  await mutate(SESSION_KEY, user, { revalidate: false });
  return user;
}

export async function logout(): Promise<void> {
  try {
    await apiPost<null>("/auth/logout");
  } finally {
    disconnectRealtime();
    resetPortfolio();
    resetMarket();
    // Drop every cached response (portfolio, orders, …) so the next account starts clean.
    await mutate(() => true, undefined, { revalidate: false });
    await mutate(SESSION_KEY, null, { revalidate: false });
  }
}
