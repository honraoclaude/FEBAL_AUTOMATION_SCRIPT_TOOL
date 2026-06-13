import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next 16 route protection (proxy.ts replaces middleware.ts — RESEARCH
 * State of the Art).
 *
 * This is a coarse cookie-PRESENCE check only, never an auth authority:
 * the JWT secret lives exclusively in the API tier, which verifies the
 * signature on every request (threat T-01-13). The refresh_token cookie is
 * path-scoped to /api/auth and never visible here — silent session resume
 * is wired in the login page and lib/api/client.ts, not in proxy.ts.
 */
export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has("access_token");
  const isLogin = request.nextUrl.pathname.startsWith("/login");
  if (!hasSession && !isLogin) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (hasSession && isLogin) {
    return NextResponse.redirect(new URL("/targets", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next|favicon.ico|api).*)"] };
