/**
 * Typed fetch wrapper for the FastAPI backend.
 *
 * All calls are same-origin (the Next rewrite proxies /api/* to FastAPI), so
 * httpOnly auth cookies ride automatically — `credentials: "same-origin"` is
 * the fetch default and this module never reads or writes token values
 * (threat T-01-14: it only observes HTTP statuses).
 *
 * 401 handling implements D-04's 7-day session: refresh-once-then-retry.
 * On a 401 from any endpoint EXCEPT /api/auth/login and /api/auth/refresh,
 * POST /api/auth/refresh once (the refresh cookie is path-scoped to
 * /api/auth and rides automatically); if refresh succeeds, retry the
 * original request exactly once. Only when refresh fails OR the retry still
 * 401s do we hard-redirect to /login. A per-request `retried` flag
 * guarantees no loops and no recursive refreshes.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Endpoints whose 401s must never trigger an auto-refresh. */
const REFRESH_EXEMPT = ["/api/auth/login", "/api/auth/refresh"];

async function parseDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
    return `Request failed with status ${res.status}`;
  } catch {
    return `Request failed with status ${res.status}`;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retried = false,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });

  if (res.status === 401 && !REFRESH_EXEMPT.includes(path)) {
    if (!retried) {
      const refresh = await fetch("/api/auth/refresh", { method: "POST" });
      if (refresh.ok) {
        // New access cookie set — retry the original request exactly once.
        return request<T>(path, init, true);
      }
    }
    // Refresh failed or the retried request still 401s: session is over.
    window.location.assign("/login");
    return new Promise<T>(() => {}); // navigation in flight; never resolves
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseDetail(res));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path);
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  patch<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};
