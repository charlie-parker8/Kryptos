/**
 * The one place the frontend talks to the FastAPI backend over HTTP. Everything is
 * same-origin (the Vite dev proxy forwards `/auth` `/orders` `/portfolio` to :8000), so the
 * httponly `kryptos_session` cookie rides along on its own — no `Authorization` header, no
 * token handling here.
 *
 * Money is a decimal **string** on the wire (see `core/realtime/types.ts`); this layer never
 * parses it. A non-2xx response throws `ApiError` carrying the parsed body so callers can
 * branch on `status` (401 → session gone) or the error payload.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`API ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }

  /** FastAPI puts the human-readable message in `detail` for HTTPException responses. */
  get detail(): string | undefined {
    if (
      typeof this.body === "object" &&
      this.body !== null &&
      "detail" in this.body &&
      typeof (this.body as { detail: unknown }).detail === "string"
    ) {
      return (this.body as { detail: string }).detail;
    }
    return undefined;
  }
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<unknown> {
  const init: RequestInit = { method, credentials: "same-origin" };
  const headers: Record<string, string> = { ...extraHeaders };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  init.headers = headers;

  const response = await fetch(path, init);

  const parsed = await parseBody(response);
  if (!response.ok) throw new ApiError(response.status, parsed);
  return parsed;
}

export function apiGet<T>(path: string): Promise<T> {
  return request("GET", path) as Promise<T>;
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  return request("POST", path, body, headers) as Promise<T>;
}
