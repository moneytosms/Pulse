// Thin fetch wrapper for the Pulse API.
//
// Everything is same-origin: Caddy puts Next and FastAPI behind one host
// (ADR-0012), so requests go to a relative `/api/v1/...` path and the session
// cookie rides along with `credentials: "include"`.
//
// The wire is camelCase in both directions (backend rule: every schema is a
// PulseSchema with a camelCase alias generator), so request bodies and parsed
// responses are used as-is with no key transformation.

const API_BASE = "/api/v1";

import type { ErrorCode, ErrorDetail, ErrorBody } from "./generated/api";
export type { ErrorCode } from "./generated/api";
export type ApiErrorDetail = ErrorDetail;
export type ApiErrorBody = Pick<ErrorBody, "message"> & Partial<Omit<ErrorBody, "code" | "message">> & {
  code: ErrorCode | "NETWORK" | "GENERIC";
};

/**
 * Thrown for any non-2xx response, and for a transport failure (offline).
 * Screens render from `code` via `lib/errors.ts`, never from `message`
 * (ADR-0013) — `message` is kept only for logs.
 */
export class ApiError extends Error {
  readonly code: ApiErrorBody["code"];
  readonly status: number;
  readonly details?: ApiErrorDetail[];
  readonly requestId?: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.code);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.requestId;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Serialized as JSON. */
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: "include",
      signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    // Network / CORS / abort — no envelope to parse.
    throw new ApiError(0, { code: "NETWORK", message: String(cause) });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const isJson = response.headers
    .get("content-type")
    ?.toLowerCase()
    .includes("application/json");
  const payload = isJson ? await response.json().catch(() => undefined) : undefined;

  if (!response.ok) {
    const envelope = (payload as { error?: ApiErrorBody } | undefined)?.error;
    throw new ApiError(
      response.status,
      envelope ?? { code: "GENERIC", message: `HTTP ${response.status}` },
    );
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
};
