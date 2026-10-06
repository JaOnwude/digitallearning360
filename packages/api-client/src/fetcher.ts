/**
 * The single fetch function used by every generated endpoint.
 * - Sends cookies (session auth is cookie-based; no tokens in JS).
 * - Resolves the API base URL from NEXT_PUBLIC_API_URL.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`API request failed with status ${status}`);
  }
}

const baseUrl = (): string =>
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) || "http://api.digitallearning360.localhost:8360";

export const apiFetch = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(`${baseUrl()}${url}`, {
    ...init,
    credentials: "include",
    headers: { Accept: "application/json", ...init?.headers },
  });
  const text = await res.text();
  const body: unknown = text ? JSON.parse(text) : undefined;
  if (!res.ok) throw new ApiError(res.status, body);
  return { data: body, status: res.status, headers: res.headers } as T;
};
