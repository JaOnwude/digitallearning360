import { expect, test, type Dialog } from "@playwright/test";
import { signInParent, signInStaff, signOut, world } from "./helpers";

// Smallest valid PNG: the API checks file contents, not the name.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

/** R19–R23, AC6 and AC9: invoices → results withheld → transfer proof → bursar confirms →
 * results visible and a receipt is ready. */
test("fees: withholding, transfer proof, confirmation, receipt", async ({ page }) => {
  const w = world();

  // Bursar issues this term's invoices.
  await signInStaff(page, w.bursar.email, w.password, w.bursar.totp);
  await page.goto("/fees");
  const accept = (d: Dialog) => void d.accept(); // "Issue invoices…?", then "3 invoice(s) issued…"
  page.on("dialog", accept);
  await page.getByRole("button", { name: "Issue invoices" }).click();
  await expect(page.getByText("0 of 3")).toBeVisible(); // fully paid: JSS1 A (2) + JSS1 B (1)
  page.off("dialog", accept);
  await signOut(page);

  // Parent: results withheld with the balance shown (AC6).
  await signInParent(page, w.parent.email);
  await expect(page.getByText("Results withheld — outstanding balance ₦45,000")).toBeVisible();
  await expect(page.getByText(/Average/)).toHaveCount(0);

  // Pays by transfer and uploads the receipt.
  await page.getByRole("link", { name: /School fees/ }).first().click();
  await page.getByRole("link", { name: /First Term/ }).click();
  await expect(page.getByText("Balance")).toBeVisible();
  await page.getByRole("button", { name: "I've paid by bank transfer" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "receipt.png", mimeType: "image/png", buffer: PNG });
  await page.locator('input[name="amount"]').fill("45,000");
  await page.locator('input[name="bank_reference"]').fill("E2E-TRF-0001");
  await page.getByRole("button", { name: "Send to the bursar" }).click();
  await expect(page.getByText("Waiting for the bursar")).toBeVisible();
  await signOut(page);

  // Bursar confirms the amount that arrived (AC9).
  await signInStaff(page, w.bursar.email, w.password, w.bursar.totp);
  await page.goto("/fees/proofs");
  await expect(page.getByText(w.parent.child)).toBeVisible();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByLabel("Amount received (₦)")).toHaveValue("45000");
  await page.getByRole("button", { name: "Confirm payment" }).click();
  await expect(page.getByText("Nothing to check. All caught up.")).toBeVisible();
  await signOut(page);

  // Parent: paid, receipt downloadable, results visible again.
  await signInParent(page, w.parent.email);
  await expect(page.getByText(/Average 82/)).toBeVisible();
  await page.goto("/fees");
  await page.getByRole("link", { name: /First Term/ }).click();
  await expect(page.getByText("E2E-TRF-0001").first()).toBeVisible();
  const receipt = page.getByRole("link", { name: "Receipt" });
  const href = await receipt.getAttribute("href");
  const pdf = await page.request.get(href!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
});
