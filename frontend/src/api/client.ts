import type { components } from "./schema";

/** The API's request and response bodies, generated from its OpenAPI schema. */
export type S = components["schemas"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Full-page navigation, in one place so tests can replace it. */
export const nav = {
  to(url: string): void {
    location.assign(url);
  },
};

/** A URL inside the app. Relative to <base href>, which the server sets to the mount path. */
export function appUrl(path = ""): string {
  return new URL(path, document.baseURI).href;
}

export function apiUrl(path: string): string {
  return appUrl(`api/${path}`);
}

export function request(method: string, body?: unknown, signal?: AbortSignal): RequestInit {
  const headers: Record<string, string> = { "X-Requested-With": "nlab" }; // the server's CSRF check
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return {
    method,
    credentials: "same-origin",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  };
}

export async function failure(response: Response): Promise<ApiError> {
  if (response.status === 401) nav.to(appUrl("signin"));
  let message = `Request failed (${response.status})`;
  try {
    const { detail } = await response.json();
    if (typeof detail === "string") message = detail;
    // FastAPI's validation errors ({msg}) or the scenario validator's issues ({path, message})
    else if (Array.isArray(detail)) message = detail.map((item) => item.message ?? item.msg ?? String(item)).join("; ");
  } catch {
    // not JSON: keep the status message
  }
  return new ApiError(response.status, message);
}

/** Dispatched when a model action settles (a mutating call or a streamed turn), once per request: the header's
 * token bar refetches. Never dispatched per stream chunk. */
export const SPENT = "nlab:spent";
export function spent(): void {
  window.dispatchEvent(new Event(SPENT));
}

export async function api<T = void>(path: string, init: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const method = init.method ?? "GET";
  const response = await fetch(apiUrl(path), request(method, init.body, init.signal));
  if (method !== "GET") spent(); // the call may have used tokens
  if (!response.ok) throw await failure(response);
  return (response.status === 204 ? undefined : await response.json()) as T;
}
