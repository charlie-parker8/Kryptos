import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { ApiError } from "@/core/api/client";
import { register } from "@/core/auth/api";
import { useSession } from "@/core/auth/useSession";
import { AuthField } from "./AuthField";

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409)
      return "That email is already registered — sign in instead.";
    if (error.status === 422)
      return "Enter a valid email and a password of at least 8 characters.";
    if (error.status >= 500)
      return "Can't reach the server right now — try again in a moment.";
    return error.detail ?? "Something went wrong. Try again.";
  }
  return "Can't reach the server right now — try again in a moment.";
}

export function RegisterScreen() {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isLoading && isAuthenticated) return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(messageFor(err));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-sm font-semibold text-fg-strong">Create an account</h1>
      <p className="text-xs leading-relaxed text-muted">
        You start with a fake $100,000. Trade BTC, ETH, and SOL at live prices.
      </p>

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
        autoComplete="new-password"
        required
        minLength={8}
        maxLength={72}
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
        {submitting ? "Creating…" : "Create account"}
      </button>

      <p className="text-center text-xs text-muted">
        Already have an account?{" "}
        <Link to="/login" className="text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
