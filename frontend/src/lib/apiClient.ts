/**
 * Thin wrapper around fetch() that centralises:
 *   - JSON content-type headers
 *   - error → message parsing (FastAPI's { detail: "..." } shape)
 *   - HTTP-status → typed Error so callers get a useful .message
 *
 * Callers do `await api.get<T>("/api/v1/foo")` instead of hand-rolling
 * fetch + .ok check + .json() in every component.
 *
 * Keep this file boring. Don't add caching, auth, retry, or anything that
 * varies per-call — pass them through the options argument.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(status: number, url: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
  }
}

type Method = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";

interface RequestOptions {
  signal?: AbortSignal;
  /** Override Content-Type / Accept / etc. for unusual endpoints. */
  headers?: Record<string, string>;
}

async function request<T>(method: Method, url: string, body?: unknown, opts?: RequestOptions): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(opts?.headers ?? {}) };
  let init: RequestInit = { method, headers, signal: opts?.signal };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init = { ...init, body: JSON.stringify(body) };
  }

  const res = await fetch(url, init);

  // 204 No Content
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    // FastAPI errors are { detail: string | array }. Anything else, fall back to status text.
    let message = `HTTP ${res.status}`;
    if (data && typeof data === "object" && "detail" in (data as Record<string, unknown>)) {
      const detail = (data as { detail: unknown }).detail;
      message = typeof detail === "string" ? detail : JSON.stringify(detail);
    } else if (typeof data === "string" && data) {
      message = data;
    } else if (res.statusText) {
      message = `HTTP ${res.status}: ${res.statusText}`;
    }
    throw new ApiError(res.status, url, message);
  }

  return data as T;
}

export const api = {
  get: <T>(url: string, opts?: RequestOptions) => request<T>("GET", url, undefined, opts),
  post: <T>(url: string, body?: unknown, opts?: RequestOptions) => request<T>("POST", url, body, opts),
  put: <T>(url: string, body?: unknown, opts?: RequestOptions) => request<T>("PUT", url, body, opts),
  patch: <T>(url: string, body?: unknown, opts?: RequestOptions) => request<T>("PATCH", url, body, opts),
  del: <T>(url: string, opts?: RequestOptions) => request<T>("DELETE", url, undefined, opts),
};
