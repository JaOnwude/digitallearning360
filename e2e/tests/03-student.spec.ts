import { expect, test } from "@playwright/test";
import { world } from "./helpers";

/** AC2: a student with an initial password must change it, then sees only their own results. */
test("student changes initial password and sees only their own results", async ({ page }) => {
  const w = world();
  await page.goto("/login");
  await page.getByRole("tab", { name: "Student" }).click();
  await page.getByLabel("Admission number").fill(w.student.admission_no);
  await page.getByLabel("Password", { exact: true }).fill(w.password);
  await page.getByLabel("Password", { exact: true }).press("Enter");

  await expect(page).toHaveURL(/\/change-password/);
  await page.goto("/dashboard"); // can't skip it
  await expect(page).toHaveURL(/\/change-password/);
  const next = "a-brand-new-pass-42";
  await page.getByLabel("New password").fill(next);
  await page.getByLabel("Type it again").fill(next);
  await page.getByLabel("Type it again").press("Enter");

  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText("Your results")).toBeVisible();
  await expect(page.getByText(/Average 82/)).toBeVisible();
  await expect(page.getByText(w.parent.other_child)).toHaveCount(0);
});
