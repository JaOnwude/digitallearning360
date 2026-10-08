import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";
import { OUTBOX_FILE, WORLD_FILE } from "../paths";

/** Accounts and names created by apps/api/tests/e2e_world.py for this run. */
export type World = {
  slug: string;
  school: string;
  password: string;
  admin: { email: string; totp: string };
  bursar: { email: string; totp: string };
  teacher: { email: string };
  parent: { email: string; child: string; other_child: string };
  student: { admission_no: string; name: string };
  arm_b: { id: string; label: string; student: string };
  subjects: string[];
};

export const world = (): World => JSON.parse(readFileSync(WORLD_FILE, "utf8")) as World;

// ---------------------------------------------------------------- TOTP (RFC 6238)

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  return Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
}

function totpAt(secret: string, step: number): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const mac = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = mac[mac.length - 1] & 0xf;
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

const usedSteps = new Map<string, number>();

/** A code the API hasn't seen yet: codes are single use, so wait for the next one if needed. */
export async function freshTotp(secret: string): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  while ((usedSteps.get(secret) ?? -1) >= step) {
    await new Promise((r) => setTimeout(r, 1_000));
    step = Math.floor(Date.now() / 30_000);
  }
  usedSteps.set(secret, step);
  return totpAt(secret, step);
}

// ---------------------------------------------------------------- sign-in flows

export async function signInStaff(page: Page, email: string, password: string, totpSecret?: string) {
  await page.goto("/login");
  await page.getByRole("tab", { name: "Staff" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Password", { exact: true }).press("Enter");
  if (totpSecret) {
    await expect(page).toHaveURL(/\/two-factor/);
    await page.getByLabel("Code").fill(await freshTotp(totpSecret));
    await page.getByLabel("Code").press("Enter");
  }
  await expect(page).toHaveURL(/\/dashboard/);
}

/** The newest one-time code emailed to `email` (the e2e API writes emails to a file). */
function latestCode(email: string): string | null {
  const lines = readFileSync(OUTBOX_FILE, "utf8").trim().split("\n").filter(Boolean);
  for (const line of lines.reverse()) {
    const msg = JSON.parse(line) as { to: string; text: string };
    const code = msg.to === email ? /\b(\d{6})\b/.exec(msg.text)?.[1] : undefined;
    if (code) return code;
  }
  return null;
}

export async function signInParent(page: Page, email: string) {
  const before = latestCode(email);
  await page.goto("/login");
  await page.getByLabel("Your email").fill(email);
  await page.getByRole("button", { name: /sign-in code/i }).click();
  let code: string | null = null;
  await expect.poll(() => (code = latestCode(email)) !== null && code !== before).toBe(true);
  await page.getByLabel("Sign-in code").fill(code!);
  await page.getByLabel("Sign-in code").press("Enter");
  await expect(page).toHaveURL(/\/dashboard/);
}

export async function signOut(page: Page) {
  await page.context().clearCookies();
}
