import { LegalPage } from "./LegalPage";

export function PrivacyScreen() {
  return (
    <LegalPage title="Privacy Policy" updated="August 28, 2026">
      <p>
        Kryptos collects as little as possible — just what an account needs to work. There
        are no third-party analytics, advertising, or tracking of any kind.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li><strong>Email address</strong> — to sign you in and, if needed, to reach you about your account.</li>
        <li><strong>Username</strong> — your public display name on the leaderboard. Don&apos;t use your real name if you&apos;d rather it not be public.</li>
        <li><strong>Password</strong> — stored only as a bcrypt hash. We never see or store the plain text.</li>
        <li><strong>A session cookie</strong> (<code>kryptos_session</code>) — httponly, set after you sign in so you stay signed in. It is not used for tracking.</li>
        <li><strong>Basic server logs</strong> — request metadata (IP, timestamp, path) kept briefly for security and debugging.</li>
      </ul>
      <p>
        Your trading activity (positions, cash, ledger) is game data tied to your account.
        Your username and equity appear on the public leaderboard.
      </p>

      <h2>What we don&apos;t do</h2>
      <ul>
        <li>No analytics scripts, ad networks, tracking pixels, or third-party cookies.</li>
        <li>No selling, renting, or sharing your data with advertisers or data brokers.</li>
        <li>No profiling beyond what the game itself shows.</li>
      </ul>

      <h2>Where your data lives</h2>
      <p>
        Account and game data is stored in a PostgreSQL database hosted on Supabase, with
        ephemeral cache data on Render Key Value. The application runs on Render. These
        providers process data on our behalf, in the United States.
      </p>

      <h2>Retention and deletion</h2>
      <p>
        We keep your data while your account exists. You can ask us to delete your account
        and its personal data at any time — email{" "}
        <a href="mailto:charlie8parker@gmail.com">charlie8parker@gmail.com</a> from your
        registered address. Note that accounts and data may also be reset or removed as
        part of running this hobby project.
      </p>

      <h2>Children</h2>
      <p>
        Kryptos is not directed at children and is not intended for anyone under 16.
      </p>

      <h2>Changes</h2>
      <p>
        This policy may be updated; the &ldquo;last updated&rdquo; date above reflects the
        current version.
      </p>

      <h2>Contact</h2>
      <p>
        Privacy questions or requests:{" "}
        <a href="mailto:charlie8parker@gmail.com">charlie8parker@gmail.com</a>.
      </p>
    </LegalPage>
  );
}
