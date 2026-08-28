/**
 * Milestone A benchmark: WebSocket tick-to-client latency (backs resume bullet 1).
 *
 * Each VU opens an authenticated `/ws` connection and, for every `price_tick` frame,
 * records `Date.now() - broadcast_at` — the field the backend stamps in
 * `price_stream.handle_tick` (`app/ws_messages.py::PriceTickMessage.broadcast_at`). The
 * threshold finds the max concurrency the single-process in-process fan-out sustains
 * under a p95 latency bound.
 *
 * Prereqs: `docker compose up -d`, backend on :8000 with a live Kraken WS connection
 * (real ticks — run against a machine with internet). Then:
 *
 *   k6 run backend/benchmarks/k6/ws_latency.js
 *   VUS=200 DURATION=90s k6 run backend/benchmarks/k6/ws_latency.js
 *
 * Record the p95/p99 of `ws_tick_latency_ms` and the VU count into
 * backend/benchmarks/RESULTS.md.
 */

import http from "k6/http";
import ws from "k6/ws";
import { check } from "k6";
import { Trend, Counter } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const WS_BASE = __ENV.WS_URL || "ws://localhost:8000/ws";

const tickLatency = new Trend("ws_tick_latency_ms", true);
const ticksSeen = new Counter("ws_ticks_seen");

export const options = {
  scenarios: {
    sustained: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 50),
      duration: __ENV.DURATION || "60s",
    },
  },
  thresholds: {
    ws_tick_latency_ms: ["p(95)<250", "p(99)<750"],
    ws_ticks_seen: ["count>100"],
  },
};

export function setup() {
  const suffix = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  const res = http.post(
    `${BASE}/auth/register`,
    JSON.stringify({
      email: `k6ws_${suffix}@example.com`,
      username: `k6ws_${suffix}`.slice(0, 32),
      password: "correct-horse-1",
    }),
    { headers: { "Content-Type": "application/json" } },
  );
  check(res, { registered: (r) => r.status === 201 });
  return { cookie: res.cookies["kryptos_session"][0].value };
}

export default function (data) {
  const res = ws.connect(
    WS_BASE,
    { headers: { Cookie: `kryptos_session=${data.cookie}` } },
    (socket) => {
      socket.on("message", (raw) => {
        let msg;
        try {
          msg = JSON.parse(raw);
        } catch {
          return;
        }
        if (msg.type === "price_tick" && typeof msg.broadcast_at === "number") {
          tickLatency.add(Date.now() - msg.broadcast_at);
          ticksSeen.add(1);
        }
      });
      socket.setTimeout(() => socket.close(), 55_000);
    },
  );
  check(res, { "ws 101": (r) => r && r.status === 101 });
}
