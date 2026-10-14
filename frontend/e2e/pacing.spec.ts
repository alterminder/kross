import { expect, test } from "@playwright/test";

test("an author sets a scenario's pacing in the editor and the server accepts it", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=admin");
  await page.locator("a.cover-card", { hasText: "Access to an IDP camp" }).first().click(); // the curated one: an earlier test saved a copy
  await page.getByRole("link", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Pacing" })).toBeVisible(); // under Basics

  await page.getByRole("button", { name: "Start from the built-in stages" }).click();
  await expect(page.getByRole("list", { name: "Stages on a timeline" })).toContainText("Exploration");
  await page.getByLabel("Stage 1 label").fill("Cold start");
  await page.getByLabel("Stage 1 allows twists").uncheck();
  await page.getByLabel("Warning minutes").fill("3, 1");
  await page.getByRole("radio", { name: "The trainer decides" }).check();
  await page.getByLabel("Silence after seconds").fill("45");
  await page.getByLabel("Silence line").fill("Was there anything else?");

  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("No problems found.")).toBeVisible();

  // a stage with no instruction is a problem the server names
  await page.getByLabel("Stage 3 instruction").fill("");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("No problems found.")).toHaveCount(0);
});
