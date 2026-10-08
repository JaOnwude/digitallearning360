import { NextResponse, type NextRequest } from "next/server";
import { slugFromHost } from "@/lib/tenant";

/**
 * Runs before every request (spec: same-origin API + subdomain tenancy).
 *
 * 1. `/api/*` → rewritten to the FastAPI service, with headers proving it came through us.
 *    The browser therefore only ever talks to the school's own origin: cookies stay
 *    host-only per school and no CORS is needed.
 * 2. Pages on a school host → rewritten to `/s/{slug}/...`, so pages get the school as a
 *    route param. The address bar keeps the clean URL.
 */
const API_URL = process.env.DL360_API_INTERNAL_URL ?? "http://127.0.0.1:8360";
const PROXY_KEY = process.env.DL360_PROXY_KEY ?? "dev-proxy-key-change-me";

export function proxy(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const { pathname, search } = request.nextUrl;

  // Never trust client-supplied versions of our internal headers.
  const headers = new Headers(request.headers);
  for (const name of [...headers.keys()]) {
    if (name.startsWith("x-dl360-")) headers.delete(name);
  }

  if (pathname.startsWith("/api/")) {
    headers.set("x-dl360-host", host);
    headers.set("x-dl360-proxy-key", PROXY_KEY);
    return NextResponse.rewrite(new URL(pathname + search, API_URL), { request: { headers } });
  }

  // Pages get a per-request CSP nonce; Next applies it to its own scripts while rendering.
  const csp = contentSecurityPolicy();
  headers.set("content-security-policy", csp);

  const slug = slugFromHost(host);
  let response: NextResponse;
  if (slug === null) {
    response = NextResponse.next({ request: { headers } }); // marketing site
  } else if (pathname.startsWith("/s/")) {
    // Internal paths are not addressable from the browser.
    return new NextResponse("Not found", { status: 404 });
  } else {
    const url = request.nextUrl.clone();
    url.pathname = `/s/${slug}${pathname === "/" ? "" : pathname}`;
    response = NextResponse.rewrite(url, { request: { headers } });
  }
  response.headers.set("content-security-policy", csp);
  return response;
}

const DEV = process.env.NODE_ENV === "development";
// Browser error reports go straight to Sentry's ingest (spec R27), when configured.
const SENTRY_ORIGIN = process.env.NEXT_PUBLIC_SENTRY_DSN ? new URL(process.env.NEXT_PUBLIC_SENTRY_DSN).origin : "";

/**
 * Scripts: only ours, via a fresh nonce (`strict-dynamic` lets them load their chunks).
 * Styles allow inline because each school's brand colours are injected as a <style> block.
 * API calls, PDFs, uploads and SSE are all same-origin through this proxy.
 */
function contentSecurityPolicy(): string {
  const nonce = btoa(crypto.randomUUID());
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${DEV ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src 'self'${SENTRY_ORIGIN ? ` ${SENTRY_ORIGIN}` : ""}${DEV ? " ws:" : ""}`,
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(DEV ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

export const config = {
  matcher: [
    // Every API call, including ones that look like files (e.g. /api/reports/{id}.pdf).
    "/api/:path*",
    // Pages: skip Next internals and static files (anything with a file extension).
    "/((?!_next/|favicon.ico|.*\\.[a-zA-Z0-9]+$).*)",
  ],
};
