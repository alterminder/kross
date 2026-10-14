import { expect, test } from "@playwright/test";

test("a new user signs in, plays a curated scenario and reads the debrief", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=alice");

  const cards = page.locator("a.cover-card");
  const response = await page.request.get("api/scenarios", { headers: { "X-Requested-With": "nlab" } });
  expect(response.ok()).toBe(true);
  const scenarios = (await response.json()) as unknown[];
  expect(scenarios.length).toBeGreaterThan(0);
  await expect(cards).toHaveCount(scenarios.length);
  await expect(cards.first()).toHaveCSS("background-image", /covers\/\w+\.webp/);
  const cover = await page.request.get("covers/checkpoint.webp");
  expect(cover.ok()).toBe(true);
  expect(cover.headers()["content-type"]).toBe("image/webp");

  await cards.first().click();
  await page.getByRole("button", { name: "Start" }).click();
  await page.getByRole("button", { name: "What we know", exact: true }).click();
  await page.getByRole("button", { name: "Objective", exact: true }).click();
  await page.getByRole("button", { name: "Enter Negotiation →" }).click();
  await page.getByLabel("Your message").fill("Good morning. We would like to talk about access for the convoy.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("I hear you. Go on.")).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "End session" }).click();
  await expect(page.getByRole("heading", { name: "Debrief", exact: true })).toBeVisible();
  await expect(page.getByText("A short debrief.")).toBeVisible({ timeout: 20_000 });
});
