/**
 * The single fetch function used by every generated endpoint (browser side).
 * - Same-origin: requests go to `/api/...` on the school's own host; the Next.js proxy
 *   forwards them to the API. No CORS, and cookies stay host-only per school.
 * - Sends the double-submit CSRF token on mutations.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(ApiError.describe(status, body));
  }

  /** A human-readable message from FastAPI's `{detail}` (string or validation list). */
  static describe(status: number, body: unknown): string {
    const detail = (body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0].msg === "string") {
      const msg: string = detail[0].msg;
      if (msg.includes("valid email")) return "Enter a valid email address.";
      return msg.replace(/^Value error, /, "");
    }
    if (status === 429) return "Too many attempts. Please wait and try again.";
    if (status >= 500) return "Something went wrong on our side. Please try again.";
    return `Request failed (${status})`;
  }
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

function csrfToken(): string | undefined {
  return readCookie("__Host-dl360_csrf") ?? readCookie("dl360_csrf");
}

export const apiFetch = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (!SAFE.has(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const res = await fetch(url, { ...init, method, headers, credentials: "same-origin" });
  const text = await res.text();
  const body: unknown = text ? JSON.parse(text) : undefined;
  if (!res.ok) throw new ApiError(res.status, body);
  return { data: body, status: res.status, headers: res.headers } as T;
};
