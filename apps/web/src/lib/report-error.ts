/**
 * Browser error reporting to Sentry (spec R27), without the Sentry SDK.
 *
 * The SDK adds tens of KB to every route; parent pages must stay under 170 KB of JS. This
 * sends the same "envelope" Sentry's ingest accepts, with no personal data: no cookies,
 * no query strings, no user identifiers. Off unless NEXT_PUBLIC_SENTRY_DSN is set.
 */

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;
const ENVIRONMENT = process.env.NEXT_PUBLIC_DL360_ENV ?? process.env.NODE_ENV;
const MAX_PER_PAGE = 10; // a render loop must not flood the quota

let sent = 0;

function endpoint(dsn: string): string | null {
  try {
    const url = new URL(dsn);
    const project = url.pathname.replace(/^\//, "");
    return `${url.origin}/api/${project}/envelope/?sentry_key=${url.username}&sentry_version=7`;
  } catch {
    return null;
  }
}

const ENDPOINT = DSN ? endpoint(DSN) : null;

function frames(stack: string | undefined) {
  // "at fn (https://host/_next/static/chunks/x.js:1:234)" → Sentry frames, innermost last.
  return (stack ?? "")
    .split("\n")
    .map((line) => line.match(/at (?:(.+?) \()?(.+?):(\d+):(\d+)\)?$/))
    .filter((m): m is RegExpMatchArray => m !== null)
    .map(([, fn, file, line, col]) => ({ function: fn || "?", filename: file, lineno: Number(line), colno: Number(col) }))
    .reverse();
}

export function reportError(error: unknown, context: Record<string, string> = {}): void {
  if (!ENDPOINT || !DSN || sent >= MAX_PER_PAGE || typeof window === "undefined") return;
  sent += 1;
  const err = error instanceof Error ? error : new Error(String(error));
  const eventId = crypto.randomUUID().replaceAll("-", "");
  const event = {
    event_id: eventId,
    timestamp: Date.now() / 1000,
    platform: "javascript",
    level: "error",
    environment: ENVIRONMENT,
    tags: { side: "web", ...context },
    request: { url: location.origin + location.pathname }, // no query string: may hold references
    exception: { values: [{ type: err.name, value: err.message.slice(0, 500), stacktrace: { frames: frames(err.stack) } }] },
  };
  const body = [JSON.stringify({ event_id: eventId, dsn: DSN }), JSON.stringify({ type: "event" }), JSON.stringify(event)].join("\n");
  // text/plain keeps this a "simple" request (no preflight); keepalive survives page unloads.
  void fetch(ENDPOINT, { method: "POST", body, keepalive: true, credentials: "omit", headers: { "Content-Type": "text/plain" } }).catch(() => {});
}

/** Catch what no error boundary sees: event handlers, timers, rejected promises. */
export function installGlobalErrorReporting(): () => void {
  const onError = (e: ErrorEvent) => reportError(e.error ?? e.message, { source: "window.onerror" });
  const onRejection = (e: PromiseRejectionEvent) => reportError(e.reason, { source: "unhandledrejection" });
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  // AC12 check: run `dl360SentryTest()` in the browser console on staging/production.
  (window as unknown as { dl360SentryTest: () => void }).dl360SentryTest = () =>
    reportError(new Error("DigitalLearning360 Sentry test error (frontend)"), { source: "manual-test" });
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
