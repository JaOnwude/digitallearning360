/** Money is integer kobo everywhere; these are the only conversions to and from naira. */

const formatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

/** 4500000 → "₦45,000" (shows kobo only when there are any). */
export function naira(kobo: number): string {
  return formatter.format(kobo / 100);
}

/** "45,000" / "45000.50" / "₦45,000" → 4500000 kobo. Null if it isn't a valid amount. */
export function toKobo(input: string): number | null {
  const cleaned = input.replace(/[₦,\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}
