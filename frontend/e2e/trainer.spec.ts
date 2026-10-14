import { expect, test } from "@playwright/test";

test("a trainer playtests, steers with sliders and twists, comments and reviews the debrief", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=admin");

  // open a curated scenario and playtest it
  await page.locator("a.cover-card").first().click();
  await page.getByRole("button", { name: "Playtest" }).click();
  await page.getByRole("button", { name: "Skip to negotiation" }).click();
  await page.getByLabel("Your message").fill("Good morning. We would like to talk about access for the convoy.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("I hear you. Go on.")).toBeVisible();

  // open the trainer view: the transcript, one slider per dial
  await page.getByRole("link", { name: "Open trainer view" }).click();
  const watch = page.locator(".session-layout .console"); // Play's panel has the same sliders: anchor on Watch before counting
  const trust = watch.getByRole("slider", { name: /trust/ });
  await expect(trust).toBeVisible();
  const dials = await watch.getByRole("slider").count();

  // move the trust slider; the value persists after a reload
  const before = Number(await trust.getAttribute("value"));
  for (let i = 1; i <= 5; i++) {
    const committed = page.waitForResponse(
      (response) => response.url().includes("/dials") && response.request().method() === "POST",
    ); // each POST is an absolute set: wait for it so rapid presses cannot arrive out of order
    await trust.press("ArrowUp");
    await committed;
    await expect(trust).toHaveAttribute("value", String(before + i)); // each step lands before the next key
  }
  await page.reload();
  await expect(watch.getByRole("slider", { name: /trust/ })).toHaveAttribute("value", String(before + 5));

  // fire a preset twist
  await page.getByRole("button", { name: "Military objects" }).click();
  await expect(page.getByRole("button", { name: "Military objects" })).toBeDisabled();

  // the Debrief tab: one line per dial, a twist mark, the turn review
  await page.getByRole("tab", { name: "Debrief" }).click();
  await expect(page.getByText(/In progress, turn 1/)).toBeVisible();
  await expect(page.locator(".recharts-line-curve")).toHaveCount(dials);
  await expect(page.locator("svg").getByText("Military objects")).toBeVisible(); // the orange twist mark

  // comment on turn 1
  await page.getByLabel("Add review comment").fill("Good opener");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.locator("p.comment").getByText("Good opener")).toBeVisible();

  // the frozen prompt of turn 1
  await page.getByText("What the counterpart model was sent").click();
  await expect(page.getByText(/model test-model/)).toBeVisible();
});

test("Watch's console collapses to one column on phones, Play keeps its 300px sidebar", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=admin");
  await page.locator("a.cover-card").first().click();
  await page.getByRole("button", { name: "Playtest" }).click();
  await page.getByRole("button", { name: "Skip to negotiation" }).click();

  // Play at 900px: the console stays a 300px single-column sidebar
  await page.setViewportSize({ width: 900, height: 800 });
  const sidebar = page.locator("aside.console");
  await expect(sidebar.getByRole("slider", { name: /trust/ })).toBeVisible();
  expect(await sidebar.evaluate((el) => getComputedStyle(el).display)).toBe("block");
  expect((await sidebar.boundingBox())!.width).toBe(300);

  // Watch at 390px: one column, the console spans the full width
  await page.getByRole("link", { name: "Open trainer view" }).click();
  await page.setViewportSize({ width: 390, height: 800 });
  const console_ = page.locator(".session-layout aside.console");
  await expect(console_.getByRole("slider", { name: /trust/ })).toBeVisible();
  expect(await console_.evaluate((el) => getComputedStyle(el).display)).toBe("block");
  expect((await console_.boundingBox())!.width).toBeGreaterThan(320);
});
