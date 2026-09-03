/**
 * Auth actions. Each one hits the backend, then refreshes the SWR session cache so the
 * route guard and shell re-render against the new state. The backend sets / clears the
 * httponly `kryptos_session` cookie itself — nothing to store client-side.
 */

import { mutate } from "swr";

import { apiPost } from "@/core/api/client";
import type { SessionUser } from "@/core/api/types";
import { disconnectRealtime } from "@/core/realtime/connectRealtime";
import { resetAccount } from "@/core/state/accountStore";
import { resetBankruptcy } from "@/core/state/bankruptcyStore";
import { resetCandles } from "@/core/state/candleStore";
import { resetMarket } from "@/core/state/marketStore";
import { resetPositionEvent } from "@/core/state/positionEventStore";
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
  username: string,
  password: string,
): Promise<SessionUser> {
  const user = await apiPost<SessionUser>("/auth/register", {
    email,
    username,
    password,
  });
  await mutate(SESSION_KEY, user, { revalidate: false });
  return user;
}

export async function requestVerificationEmail(): Promise<void> {
  await apiPost<null>("/auth/verify/request");
}

export async function confirmVerification(token: string): Promise<SessionUser> {
  const user = await apiPost<SessionUser>("/auth/verify/confirm", { token });
  await mutate(SESSION_KEY, user, { revalidate: false });
  return user;
}

export async function logout(): Promise<void> {
  try {
    await apiPost<null>("/auth/logout");
  } finally {
    disconnectRealtime();
    resetAccount();
    resetMarket();
    resetCandles();
    resetBankruptcy();
    resetPositionEvent();
    // Drop every cached response (account, positions, …) so the next account starts clean.
    await mutate(() => true, undefined, { revalidate: false });
    await mutate(SESSION_KEY, null, { revalidate: false });
  }
}
