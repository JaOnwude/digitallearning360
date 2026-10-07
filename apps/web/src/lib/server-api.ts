import "server-only";
import { cookies } from "next/headers";
import { BASE_DOMAIN } from "@/lib/tenant";

const API_URL = process.env.DL360_API_INTERNAL_URL ?? "http://127.0.0.1:8360";
const PROXY_KEY = process.env.DL360_PROXY_KEY ?? "dev-proxy-key-change-me";

/**
 * Call the API from a Server Component for a given school, forwarding the user's cookies.
 * Uses the canonical school host, so it works the same behind any public hostname.
 */
export async function serverFetch<T>(slug: string, path: string): Promise<T | null> {
  const cookieHeader = (await cookies()).toString();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: {
        accept: "application/json",
        "x-dl360-host": `${slug}.${BASE_DOMAIN}`,
        "x-dl360-proxy-key": PROXY_KEY,
        ...(cookieHeader ? { cookie: cookieHeader } : {}),
      },
      cache: "no-store",
    });
  } catch (cause) {
    // API down or still waking up: shown by app/s/error.tsx as a friendly retry page.
    console.error(`API unreachable at ${API_URL}`, cause);
    throw new Error("API_UNREACHABLE");
  }
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${path} failed with ${res.status}`);
  return (await res.json()) as T;
}
