import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError } from "@/core/api/client";
import { confirmVerification } from "@/core/auth/api";
import { useSession } from "@/core/auth/useSession";

type State = "working" | "ok" | "invalid" | "throttled" | "error";

export function VerifyScreen() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { isAuthenticated } = useSession();
  const [state, setState] = useState<State>(token ? "working" : "invalid");
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true; // StrictMode double-invoke guard — the token is single-use
    confirmVerification(token)
      .then(() => setState("ok"))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 400) setState("invalid");
        else if (err instanceof ApiError && err.status === 429) setState("throttled");
        else setState("error");
      });
  }, [token]);

  return (
    <div className="space-y-4">
      <h1 className="text-sm font-semibold text-fg-strong">Email verification</h1>
      {state === "working" && (
        <p className="text-xs text-muted">Confirming your email…</p>
      )}
      {state === "ok" && (
        <p className="text-xs text-up">
          Your email is verified.{" "}
          <Link to="/" className="text-accent hover:underline">
            Go to your dashboard
          </Link>
          .
        </p>
      )}
      {state === "invalid" && (
        <p className="text-xs text-down">
          This link is invalid or has expired.{" "}
          <Link
            to={isAuthenticated ? "/" : "/login"}
            className="text-accent hover:underline"
          >
            {isAuthenticated ? "Open the app" : "Sign in"}
          </Link>{" "}
          and request a new one.
        </p>
      )}
      {state === "throttled" && (
        <p className="text-xs text-down">Too many attempts — try again shortly.</p>
      )}
      {state === "error" && (
        <p className="text-xs text-down">
          Something went wrong. Try the link again in a moment.
        </p>
      )}
    </div>
  );
}
