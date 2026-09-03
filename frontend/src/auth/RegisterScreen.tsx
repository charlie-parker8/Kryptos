import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { ApiError } from "@/core/api/client";
import { register } from "@/core/auth/api";
import { useSession } from "@/core/auth/useSession";
import { Button } from "@/core/primitives/Button";
import { AuthField } from "./AuthField";

const USERNAME_RE = /^[A-Za-z0-9._-]+$/;

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409)
      return error.detail === "Username already taken"
        ? "That username is taken — pick another."
        : "That email is already registered — sign in instead.";
    if (error.status === 422)
      return "Check your email, a username of 3–32 letters/numbers, and a password of at least 8 characters.";
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
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isLoading && isAuthenticated) return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (username.length < 3 || username.length > 32 || !USERNAME_RE.test(username)) {
      setError("Username must be 3–32 characters: letters, numbers, dot, dash or underscore.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await register(email, username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(messageFor(err));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <h1 className="text-base font-semibold tracking-tight text-fg-strong">
        Create an account
      </h1>
      <p className="text-xs leading-relaxed text-muted">
        You start with a fake $10,000. Go long or short on BTC, ETH, and SOL with
        leverage, priced live off Kraken.
      </p>
      <p className="text-xs leading-relaxed text-muted">
        We'll email you a link to confirm your address — verify it to open positions and
        join the leaderboard.
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
        id="username"
        label="Username"
        type="text"
        autoComplete="username"
        required
        minLength={3}
        maxLength={32}
        placeholder="shown on the leaderboard"
        value={username}
        onChange={(e) => setUsername(e.target.value.trim())}
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

      <Button variant="primary" full type="submit" disabled={submitting}>
        {submitting ? "Creating…" : "Create account"}
      </Button>

      <p className="text-center text-[0.6875rem] leading-relaxed text-muted">
        By creating an account you agree to the{" "}
        <Link to="/terms" className="text-accent hover:underline">
          Terms
        </Link>{" "}
        and{" "}
        <Link to="/privacy" className="text-accent hover:underline">
          Privacy Policy
        </Link>
        .
      </p>

      <p className="text-center text-xs text-muted">
        Already have an account?{" "}
        <Link to="/login" className="text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
