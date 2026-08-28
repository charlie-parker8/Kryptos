/**
 * Milestone C benchmark: p95/p99 read latency for GET /leaderboard under a sustained
 * concurrent read workload (backs resume bullet 3).
 *
 * The endpoint is authenticated, so setup() registers one account and reuses its
 * kryptos_session cookie for every VU. The Redis sorted set is populated by the backend's
 * periodic rebuild from every account in Postgres — to benchmark "N accounts", seed N
 * synthetic users first, e.g.:
 *
 *   docker compose up -d
 *   python -c "import asyncio,uuid; \
 *     import redis.asyncio as r; \
 *     c=r.from_url('redis://localhost:6379/0'); \
 *     asyncio.run(c.zadd('leaderboard:equity', {str(uuid.uuid4()): 1_000_000 + i for i in range(5000)}))"
 *
 * Then, with the app running on :8000:
 *   k6 run backend/benchmarks/k6/leaderboard_latency.js
 *
 * Record the p95/p99 from the summary into backend/benchmarks/RESULTS.md.
 */

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const readLatency = new Trend("leaderboard_read_ms", true);

export const options = {
  scenarios: {
    sustained_reads: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 50),
      duration: __ENV.DURATION || "60s",
    },
  },
  thresholds: {
    "leaderboard_read_ms": ["p(95)<150", "p(99)<300"],
    "http_req_failed": ["rate<0.01"],
  },
};

export function setup() {
  const suffix = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  const res = http.post(
    `${BASE}/auth/register`,
    JSON.stringify({
      email: `k6_${suffix}@example.com`,
      username: `k6_${suffix}`.slice(0, 32),
      password: "correct-horse-1",
    }),
    { headers: { "Content-Type": "application/json" } },
  );
  check(res, { "registered": (r) => r.status === 201 });
  const cookie = res.cookies["kryptos_session"][0].value;
  return { cookie };
}

export default function (data) {
  const res = http.get(`${BASE}/leaderboard?limit=100`, {
    headers: { Cookie: `kryptos_session=${data.cookie}` },
  });
  readLatency.add(res.timings.duration);
  check(res, {
    "200": (r) => r.status === 200,
    "has entries array": (r) => Array.isArray(r.json("entries")),
  });
}
