import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signInParent, world } from "./helpers";

/** AC11: no serious or critical accessibility violations on the parent pages. */
async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`)).toEqual([]);
}

test("parent pages pass axe", async ({ page }) => {
  const w = world();
  await page.goto("/login");
  await expectAccessible(page);

  await signInParent(page, w.parent.email);
  await expect(page.getByText(w.parent.child).first()).toBeVisible();
  await expectAccessible(page);

  await page.goto("/fees");
  await page.getByRole("link", { name: /First Term/ }).click();
  await expect(page.getByText("Balance")).toBeVisible();
  await expectAccessible(page);

  await page.goto("/dashboard");
  await page.getByRole("link", { name: /First Term/ }).first().click();
  await expect(page.getByText(/English/).first()).toBeVisible();
  await expectAccessible(page);
});
