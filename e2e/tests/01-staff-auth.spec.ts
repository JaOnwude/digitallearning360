import { expect, test } from "@playwright/test";
import { freshTotp, world } from "./helpers";

/** AC2: admin can't reach any page or API without two-step sign-in; no tokens in web storage. */
test("admin needs two-step sign-in before anything else", async ({ page, context }) => {
  const w = world();
  await page.goto("/login");
  await page.getByRole("tab", { name: "Staff" }).click();
  await page.getByLabel("Email", { exact: true }).fill(w.admin.email);
  await page.getByLabel("Password", { exact: true }).fill(w.password);
  await page.getByLabel("Password", { exact: true }).press("Enter");
  await expect(page).toHaveURL(/\/two-factor/);

  // Password alone opens nothing: pages bounce back, the API refuses.
  await page.goto("/students");
  await expect(page).toHaveURL(/\/two-factor/);
  const api = await page.request.get("/api/students");
  expect(api.status()).toBe(403);

  await page.getByLabel("Code").fill(await freshTotp(w.admin.totp));
  await page.getByLabel("Code").press("Enter");
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  expect((await page.request.get("/api/students")).status()).toBe(200);

  // Session cookies are httpOnly and never copied into localStorage/sessionStorage (R7).
  const secrets = (await context.cookies()).filter((c) => c.httpOnly).map((c) => c.value);
  expect(secrets.length).toBeGreaterThan(0);
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  for (const value of secrets) expect(stored).not.toContain(value);
});
