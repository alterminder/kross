import { expect, test } from "@playwright/test";

test("a visitor tries it as a guest, plays a scenario and cannot reach authoring", async ({ page }) => {
  await page.goto("signin");
  await page.getByRole("button", { name: "Try it now, no account" }).click();

  await expect(page.getByRole("note")).toContainText("You are playing as a guest");
  const response = await page.request.get("api/scenarios", { headers: { "X-Requested-With": "nlab" } });
  expect(response.ok()).toBe(true);
  const scenarios = (await response.json()) as unknown[];
  expect(scenarios.length).toBeGreaterThan(0);
  await expect(page.locator("a.cover-card")).toHaveCount(scenarios.length);
  await expect(page.getByRole("link", { name: /Add scenario/ })).toHaveCount(0);

  await page.locator("a.cover-card").first().click();
  await expect(page.getByRole("button", { name: "Playtest" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Edit" })).toHaveCount(0);
  await page.getByRole("button", { name: "Start" }).click();
  await page.getByRole("button", { name: "What we know", exact: true }).click();
  await page.getByRole("button", { name: "Objective", exact: true }).click();
  await page.getByRole("button", { name: "Enter Negotiation →" }).click();
  await page.getByLabel("Your message").fill("Good morning. We would like to talk about access for the convoy.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("I hear you. Go on.")).toBeVisible();

  // what a guest may not do is closed on the server, not just hidden
  const create = await page.request.post("api/scenarios", { data: { content: {} }, headers: { "X-Requested-With": "nlab" } });
  expect(create.status()).toBe(403);
});
