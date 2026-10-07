/**
 * Which school does a host belong to? Mirrors apps/api/app/tenancy/service.py `slug_from_host`.
 * Safe to import from the proxy (no Node-only APIs).
 */
export const BASE_DOMAIN = process.env.DL360_BASE_DOMAIN ?? "digitallearning360.localhost";
export const DEFAULT_SCHOOL_SLUG = process.env.DL360_DEFAULT_SCHOOL_SLUG || null;

const RESERVED = new Set(["www", "api", "app"]);

export function slugFromHost(host: string): string | null {
  const hostname = host.split(":")[0].toLowerCase().replace(/\.$/, "");
  const suffix = `.${BASE_DOMAIN.toLowerCase()}`;
  if (hostname.endsWith(suffix)) {
    const label = hostname.slice(0, -suffix.length);
    return label && !label.includes(".") && !RESERVED.has(label) ? label : null;
  }
  if (hostname === BASE_DOMAIN.toLowerCase()) return null; // marketing site
  return DEFAULT_SCHOOL_SLUG; // e.g. a vercel.app staging URL
}
