/**
 * Typed API client with automatic token refresh.
 *
 * Design:
 *  - Tokens live in localStorage (survives reloads) + an in-memory mirror.
 *  - On a 401, the client transparently tries ONE refresh (using the stored
 *    refresh token) and replays the request. Because the backend ROTATES
 *    refresh tokens (M3), we always persist the new pair the refresh returns.
 *  - Concurrent 401s share a single in-flight refresh (refreshPromise) so we
 *    never fire N refreshes and trip the backend's reuse-detection.
 *  - Every failure throws an ApiClientError carrying the backend's error
 *    envelope, so UI code has one error type to catch.
 */

import type { ApiError, ApiResponse, TokenPair } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "mp_access_token";
const REFRESH_KEY = "mp_refresh_token";

export class ApiClientError extends Error {
  code: string;
  status: number;
  details?: unknown;
  constructor(status: number, error: ApiError) {
    super(error.message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = error.code;
    this.details = error.details;
  }
}

// --- token storage ---
export const tokenStore = {
  get access() {
    return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY);
  },
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

let refreshPromise: Promise<boolean> | null = null;

// Exported so the XHR-based upload path (lib/upload.ts) can reuse the SAME
// refresh + coalescing logic instead of duplicating it.
export async function tryRefresh(): Promise<boolean> {
  const refresh = tokenStore.refresh;
  if (!refresh) return false;
  // Coalesce concurrent refreshes into one network call.
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!res.ok) return false;
        const body: ApiResponse<TokenPair> = await res.json();
        if (body.data) {
          tokenStore.set(body.data);
          return true;
        }
        return false;
      } catch {
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  // FormData for file uploads (skips JSON content-type).
  formData?: FormData;
  auth?: boolean; // default true
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, auth = true } = opts;

  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (auth && tokenStore.access) {
      headers["Authorization"] = `Bearer ${tokenStore.access}`;
    }
    let payload: BodyInit | undefined;
    if (formData) {
      payload = formData; // browser sets multipart boundary
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    return fetch(`${API_BASE}${path}`, { method, headers, body: payload });
  };

  let res = await doFetch();

  // Transparent one-shot refresh on 401 for authed requests.
  if (res.status === 401 && auth && tokenStore.refresh) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await doFetch();
    }
  }

  // Envelope is either {success:true,data} or {success:false,error}.
  const json = (await res.json().catch(() => null)) as
    | (ApiResponse<T> & { error?: ApiError })
    | null;

  if (!res.ok || !json?.success) {
    throw new ApiClientError(
      res.status,
      json?.error ?? { code: "UNKNOWN", message: `Request failed (${res.status})` }
    );
  }
  return json.data as T;
}

/** Full response (with pagination meta) for list endpoints. */
async function requestWithMeta<T>(path: string): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {};
  if (tokenStore.access) headers["Authorization"] = `Bearer ${tokenStore.access}`;
  let res = await fetch(`${API_BASE}${path}`, { headers });
  if (res.status === 401 && tokenStore.refresh) {
    if (await tryRefresh()) {
      headers["Authorization"] = `Bearer ${tokenStore.access}`;
      res = await fetch(`${API_BASE}${path}`, { headers });
    }
  }
  const json = (await res.json().catch(() => null)) as
    | (ApiResponse<T> & { error?: ApiError })
    | null;
  if (!res.ok || !json?.success) {
    throw new ApiClientError(
      res.status,
      json?.error ?? { code: "ERROR", message: "Request failed" }
    );
  }
  return json;
}

export const api = { request, requestWithMeta, API_BASE };
