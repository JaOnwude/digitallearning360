import { expect, test } from "@playwright/test";
import { signInStaff, world } from "./helpers";

/** A teacher types scores into the grid; they save themselves and survive a reload.
 * Published results are read-only to the teacher (AC4). */
test("teacher enters scores; published class is read-only", async ({ page }) => {
  const w = world();
  await signInStaff(page, w.teacher.email, w.password);
  await page.getByRole("link", { name: "My classes" }).first().click();

  await page.getByRole("link", { name: new RegExp(`${w.arm_b.label}\\s*${w.subjects[0]}`) }).click();
  const student = w.arm_b.student;
  const values = { "1st Assessment": "9", "2nd Assessment": "8", Project: "10", Examination: "55" };
  for (const [component, value] of Object.entries(values)) {
    await page.getByLabel(`${component} for ${student}`).fill(value);
  }
  await expect(page.getByText("All changes saved")).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(student) });
  await expect(row).toContainText("82"); // total
  await expect(row).toContainText("A"); // Distinction band

  await page.reload();
  await expect(page.getByLabel(`Examination for ${student}`)).toHaveValue("55");
  await page.getByRole("button", { name: "Mark complete" }).click();
  await expect(page.getByText("This subject is marked complete")).toBeVisible();

  // JSS1 A was published during setup: the teacher can look but not change.
  await page.goto("/classes");
  await page.getByRole("link", { name: new RegExp(`JSS1 A\\s*${w.subjects[0]}`) }).click();
  await expect(page.getByText(/read-only/)).toBeVisible();
  await expect(page.getByLabel(`Examination for ${w.parent.child}`)).toBeDisabled();
});
