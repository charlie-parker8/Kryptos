import { LegalPage } from "./LegalPage";

export function TermsScreen() {
  return (
    <LegalPage title="Terms of Use" updated="August 28, 2026">
      <p>
        Kryptos is a free crypto <strong>paper-trading game</strong>. It shows real
        market prices from Kraken, but every account uses fake money and no order ever
        reaches a real market. By using Kryptos you agree to these terms.
      </p>

      <h2>Not financial advice</h2>
      <p>
        Nothing on Kryptos is investment, financial, or trading advice. Prices, P&amp;L,
        liquidation levels, and the leaderboard exist for entertainment. Real leveraged
        trading can lose you real money quickly; do your own research before risking any.
      </p>

      <h2>Your account</h2>
      <ul>
        <li>You are responsible for keeping your password safe and for activity under your account.</li>
        <li>Your username is shown publicly on the leaderboard. Don&apos;t impersonate other people or pick something abusive.</li>
        <li>We may suspend or remove accounts that abuse the service or other users.</li>
      </ul>

      <h2>Acceptable use</h2>
      <ul>
        <li>Don&apos;t try to break, overload, or probe the service, or work around its limits.</li>
        <li>Don&apos;t script or automate trading to hammer the API.</li>
        <li>Don&apos;t scrape or redistribute the market data feed.</li>
      </ul>

      <h2>Market data and game mechanics</h2>
      <p>
        Prices are sourced from Kraken and may be delayed, incomplete, wrong, or briefly
        unavailable. Positions open, mark, and liquidate against the server&apos;s price at
        the time — a stale price blocks trading until it refreshes. If your account equity
        falls to zero it is reset to the starting balance and all positions close; this is
        part of the game.
      </p>

      <h2>Availability and changes</h2>
      <p>
        Kryptos is provided as a hobby project. We may change, pause, or shut it down at
        any time, and accounts and their data may be reset or deleted without notice.
      </p>

      <h2>Disclaimer and liability</h2>
      <p>
        Kryptos is provided &ldquo;as is&rdquo; and &ldquo;as available&rdquo;, without
        warranty of any kind. To the maximum extent permitted by law, the maintainer is
        not liable for any loss or damage arising from your use of the service.
      </p>

      <h2>Changes to these terms</h2>
      <p>
        These terms may be updated. The &ldquo;last updated&rdquo; date above changes when
        they do; continuing to use Kryptos means you accept the current version.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms:{" "}
        <a href="mailto:charlie8parker@gmail.com">charlie8parker@gmail.com</a>.
      </p>
    </LegalPage>
  );
}
