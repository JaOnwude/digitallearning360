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

  const slug = slugFromHost(host);
  if (slug === null) return NextResponse.next({ request: { headers } }); // marketing site
  if (pathname.startsWith("/s/")) {
    // Internal paths are not addressable from the browser.
    return new NextResponse("Not found", { status: 404 });
  }
  const url = request.nextUrl.clone();
  url.pathname = `/s/${slug}${pathname === "/" ? "" : pathname}`;
  return NextResponse.rewrite(url, { request: { headers } });
}

export const config = {
  // Skip Next internals and static files (anything with a file extension).
  matcher: ["/((?!_next/|favicon.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};
