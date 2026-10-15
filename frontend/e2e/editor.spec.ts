import { expect, test } from "@playwright/test";

const TITLE = "Access to an IDP camp";

/** The one nested reveal threshold the journey edits: any[{move}, {trust_gte: 55}] -> 60. */
function bumpThreshold(content: any) {
  for (const counterpart of content.counterparts ?? []) {
    for (const interest of counterpart.hidden_interests ?? []) {
      for (const member of interest.reveal_when?.any ?? []) {
        if (member.trust_gte === 55) member.trust_gte = 60;
      }
    }
  }
  return content;
}

test("the authoring journey: open a curated scenario, edit a reveal threshold, check and save an owned copy", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=admin");
  await page.locator("a.cover-card", { hasText: TITLE }).click();
  await expect(page.getByRole("link", { name: "Edit" })).toBeVisible();
  const edit = new URL(page.url()).pathname.replace(/\/$/, "") + "/edit";

  const sections = page.getByRole("tablist", { name: "Sections" });

  // 1. the editor opens with the title input within 3 s of the navigation
  const started = Date.now();
  await page.goto(edit);
  await expect(page.locator("#root_title")).toBeVisible({ timeout: 3_000 });
  expect(Date.now() - started).toBeLessThan(3_000);

  // every visible button has an accessible name, including the skill tags' icon buttons
  const form = page.locator("form.rjsf");
  await expect(form).toBeVisible();
  const buttons = form.locator("button:visible");
  for (let i = 0, count = await buttons.count(); i < count; i++) {
    await expect(buttons.nth(i)).toHaveAccessibleName(/\S/);
  }
  await expect(page.locator(".glyphicon")).toHaveCount(0);

  // 2. Counterpart: change the nested reveal threshold 55 -> 60 with the builder
  await sections.getByRole("tab", { name: "Counterpart" }).click();
  await page.getByRole("group", { name: "Trust at least 55" }).getByRole("spinbutton").fill("60");

  // 3. switch away and back: the edit survived
  await sections.getByRole("tab", { name: "Rules & twists" }).click();
  await sections.getByRole("tab", { name: "Counterpart" }).click();
  await expect(page.getByRole("group", { name: "Trust at least 60" })).toBeVisible();

  // 4. Check
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText("No problems found.")).toBeVisible();

  // 5. an owned copy: this scenario's YAML with a new id, created through the API and edited the same way
  const copySections = page.getByRole("tablist", { name: "Sections" });
  const uuid = edit.split("/")[2];
  const original = (await (await page.request.get(`api/scenarios/${uuid}`)).json()).content;
  const copy = { ...structuredClone(original), id: "e2e_authoring_copy" };
  const created = await (
    await page.request.post("api/scenarios", {
      data: { content: copy },
      headers: { "X-Requested-With": "nlab" },
    })
  ).json();
  await page.goto(`scenarios/${created.id}/edit`);
  await expect(page.locator("#root_title")).toBeVisible();
  await copySections.getByRole("tab", { name: "Counterpart" }).click();
  await page.getByRole("group", { name: "Trust at least 55" }).getByRole("spinbutton").fill("60");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("All changes saved")).toBeVisible(); // Save stays in the editor
  const savedEdit = new URL(page.url()).pathname;
  expect(savedEdit).toBe(`/scenarios/${created.id}/edit`);

  // 6. reload the copy and compare: only the threshold and the id differ
  await page.goto(savedEdit);
  // the editor restores the last section per scenario (Counterpart), so wait for the editor, not a Basics field
  await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
  await page.getByRole("tablist", { name: "Sections" }).getByRole("tab", { name: "Counterpart" }).click();
  await expect(page.getByRole("group", { name: "Trust at least 60" })).toBeVisible();
  const savedUuid = savedEdit.split("/")[2];
  const saved = (await (await page.request.get(`api/scenarios/${savedUuid}`)).json()).content;
  expect(saved).toEqual(bumpThreshold({ ...structuredClone(original), id: "e2e_authoring_copy" }));

  // 7. Arrow keys move between tabs; Tab moves into the condition threshold, regardless of the form's length.
  await page.getByRole("tab", { name: "Basics", exact: true }).click();
  await page.getByRole("tab", { name: "Basics", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  const reached = page.getByRole("tab", { name: /^Trainee brief/ });
  await expect(reached).toBeFocused();
  expect(await reached.evaluate((target) => target.matches(":focus-visible"))).toBe(true);
  await page.getByRole("tab", { name: "Counterpart" }).click();
  const condition = page.getByRole("group", { name: "Trust at least 60" });
  for (const [from, to] of [
    [condition.getByRole("combobox", { name: "Trust at least 60: comparison" }), condition.getByRole("spinbutton")],
  ]) {
    await from.focus();
    await page.keyboard.press("Tab");
    await expect(to).toBeFocused();
    expect(await to.evaluate((target) => target.matches(":focus-visible"))).toBe(true);
    await expect(to).toHaveCSS("outline-style", "solid");
  }
});

test("the editor works under the app's CSP: no schema is compiled at runtime", async ({ page }) => {
  const blocked: string[] = [];
  page.on("console", (message) => {
    if (/compiling schema|unsafe-eval/i.test(message.text())) blocked.push(message.text());
  });
  await page.goto("api/auth/dev/login?as=admin");
  await page.locator("a.cover-card", { hasText: TITLE }).first().click(); // the journey above may have added a copy
  await page.getByRole("link", { name: "Edit" }).click();
  const sections = page.getByRole("tablist", { name: "Sections" });
  for (const name of ["Counterpart", "Rules & twists", "Scoring & debrief"]) {
    await sections.getByRole("tab", { name }).click();
    await expect(sections.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true");
  }
  expect(blocked).toEqual([]);
});
