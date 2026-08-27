import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { ApiError } from "@/core/api/client";
import { login } from "@/core/auth/api";
import { useSession } from "@/core/auth/useSession";
import { AuthField } from "./AuthField";

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Invalid email or password.";
    if (error.status === 0 || error.status >= 500)
      return "Can't reach the server right now — try again in a moment.";
    return error.detail ?? "Something went wrong. Try again.";
  }
  return "Can't reach the server right now — try again in a moment.";
}

export function LoginScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, isLoading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from =
    (location.state as { from?: { pathname: string } } | null)?.from?.pathname ??
    "/";

  if (!isLoading && isAuthenticated) return <Navigate to={from} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(messageFor(err));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-sm font-semibold text-fg-strong">Sign in</h1>

      <AuthField
        id="email"
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <AuthField
        id="password"
        label="Password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />

      {error ? (
        <p
          role="alert"
          className="border border-down/40 bg-down/10 px-3 py-2 text-xs text-down"
        >
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-control bg-accent px-3 py-2 text-sm font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {submitting ? "Signing in…" : "Sign in"}
      </button>

      <p className="text-center text-xs text-muted">
        New here?{" "}
        <Link to="/register" className="text-accent hover:underline">
          Create an account
        </Link>
      </p>
    </form>
  );
}
