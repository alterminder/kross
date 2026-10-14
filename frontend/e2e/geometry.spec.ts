import { expect, test, type Page } from "@playwright/test";

test("skill tags and their input stay inside the editor at desktop and phone widths", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=admin");
  const headers = { "X-Requested-With": "nlab" };
  const cards = await (await page.request.get("api/scenarios")).json();
  const source = cards.find((card: { title: string }) => card.title === "Access to an IDP camp");
  const cloned = await page.request.post(`api/scenarios/${source.id}/duplicate`, { headers });
  expect(cloned.ok()).toBe(true);
  const scenario = await cloned.json();
  const longSkill = "Negotiation".repeat(18);
  const updated = await page.request.put(`api/scenarios/${scenario.id}`, {
    headers,
    data: { content: { ...scenario.content, skills_tested: ["Context analysis", longSkill] } },
  });
  expect(updated.ok()).toBe(true);

  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`scenarios/${scenario.id}/edit`);
    const input = page.getByRole("textbox", { name: "Skills tested" });
    await expect(input).toBeVisible();
    await input.fill("net");
    await expect(page.getByRole("button", { name: "Network Mapping", exact: true })).toBeVisible();
    const field = page.locator("[data-path='skills_tested']");
    const geometry = await field.evaluate((element) => {
      const field = element.getBoundingClientRect();
      return {
        overflow: element.scrollWidth > element.clientWidth,
        controls: [...element.querySelectorAll("input, button")].map((control) => {
          const box = control.getBoundingClientRect();
          return { left: box.left - field.left, right: box.right - field.right };
        }),
      };
    });
    expect(geometry.overflow, `tags wrap at ${width}px`).toBe(false);
    for (const control of geometry.controls) {
      expect(control.left).toBeGreaterThanOrEqual(0);
      expect(control.right).toBeLessThanOrEqual(1);
    }
    await field.screenshot({ path: `test-results/skill-tags-${width}.png` });
  }
});

/** The play page's real browser geometry (a CSS source grep cannot prove any of this):
 * Send and End session are visible without scrolling at every phone and desktop size — including with the
 * guest banner and the channel tabs on screen — the transcript keeps a usable visible area while it scrolls
 * inside, nothing overflows horizontally, and the phone layout keeps the full-width title with the actions below. */
const SIZES: [number, number][] = [
  [1280, 720],
  [390, 844],
  [390, 667],
  [320, 568],
];

function geometry(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, bottom: rect.bottom, right: rect.right };
    };
    return {
      title: box(".play-header-row h1"),
      row: box(".play-header-row"),
      actions: box(".play-header-actions"),
      send: box(".composer button"),
      end: box(".composer button.secondary"),
      transcript: box(".transcript"),
      label: document.querySelector(".transcript .who")?.textContent,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    };
  });
}

/** Send and End session sit fully inside the viewport: on screen and never clipped off a side. */
function expectComposerIn(geo: Awaited<ReturnType<typeof geometry>>, width: number, height: number) {
  for (const which of ["send", "end"] as const) {
    expect(geo[which]!.y, `${which} top at ${width}x${height}`).toBeGreaterThanOrEqual(0);
    expect(geo[which]!.bottom, `${which} bottom at ${width}x${height}`).toBeLessThanOrEqual(height);
    expect(geo[which]!.x, `${which} left at ${width}x${height}`).toBeGreaterThanOrEqual(0);
    expect(geo[which]!.right, `${which} right at ${width}x${height}`).toBeLessThanOrEqual(width);
  }
}

/** The composer must sit inside the viewport and the transcript must keep the floor it has in CSS. */
async function expectFits(page: Page, width: number, height: number) {
  const geo = await geometry(page);
  expectComposerIn(geo, width, height);
  expect(geo.horizontalOverflow, `no horizontal overflow at ${width}x${height}`).toBe(false);
  expect(geo.transcript!.height, `usable transcript at ${width}x${height}`).toBeGreaterThanOrEqual(Math.min(96, height * 0.1) - 1); // -1: 10vh resolves a hair below height/10 on fractional screens
  return geo;
}

test("play fits every viewport: the composer is visible without scrolling, the transcript scrolls inside", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=geometry");
  const list = await (await page.request.get("api/scenarios", { headers: { "X-Requested-With": "nlab" } })).json();
  const scenario = (list as { id: string; title: string }[]).find((item) => item.title === "Detained before nightfall");
  expect(scenario, "the curated detention scenario").toBeTruthy();
  const created = await page.request.post("api/sessions", {
    headers: { "X-Requested-With": "nlab" },
    data: { scenario_id: scenario!.id, mode: "solo" },
  });
  expect(created.ok()).toBe(true);
  const play = `play/${(await created.json()).id as string}`;

  for (const [width, height] of SIZES) {
    await page.setViewportSize({ width, height });
    await page.goto(play);
    await page.getByLabel("Your message").waitFor();
    await page.evaluate(() => document.fonts.ready);
    const geo = await expectFits(page, width, height);
    expect(geo.label, `speaker name at ${width}x${height}`).toBe("Captain Idris Mansour"); // the speakerless opening keeps the first counterpart's short name
    if (width <= 600) {
      expect(geo.title!.width, `title full width at ${width}x${height}`).toBeCloseTo(geo.row!.width, 0);
      expect(geo.actions!.y, `actions beneath the title at ${width}x${height}`).toBeGreaterThanOrEqual(geo.title!.bottom);
    }
  }
});

/** The playtest console stacks under the dialogue on phones: it must never overlap it (a collapsed grid row
 * puts the console on top of the transcript), and Send and End session stay visible. */
test("the playtest console follows the dialogue without overlap on phones", async ({ page }) => {
  await page.goto("api/auth/dev/login?as=admin"); // a superadmin starts a playtest session with the trainer console
  const list = await (await page.request.get("api/scenarios", { headers: { "X-Requested-With": "nlab" } })).json();
  const scenario = (list as { id: string; title: string }[]).find((item) => item.title === "Detained before nightfall");
  expect(scenario, "the curated detention scenario").toBeTruthy();
  const created = await page.request.post("api/sessions", {
    headers: { "X-Requested-With": "nlab" },
    data: { scenario_id: scenario!.id, mode: "playtest" },
  });
  expect(created.ok()).toBe(true);
  const id = (await created.json()).id as string;
  const play = `play/${id}`;
  for (let i = 0; i < 15; i += 1) {
    // 30 long transcript lines: the overlap must not return once the dialogue outgrows the screen
    const sent = await page.request.post(`api/sessions/${id}/turns`, {
      headers: { "X-Requested-With": "nlab" },
      data: { text: `Point ${i}: a deliberately long line for the phone geometry probe. ${"More words to wrap across rows. ".repeat(6)}` },
    });
    expect(sent.ok(), `turn ${i}`).toBe(true);
  }

  for (const [width, height] of [[390, 667], [320, 568]] as [number, number][]) {
    await page.setViewportSize({ width, height });
    await page.goto(play);
    await page.getByLabel("Your message").waitFor();
    await page.locator(".play.with-panel aside.console").waitFor();
    await page.evaluate(() => document.fonts.ready);
    const boxes = await page.evaluate(() => {
      const dialogue = document.querySelector(".dialogue-container")!.getBoundingClientRect();
      const panel = document.querySelector(".play.with-panel > :not(section)")!.getBoundingClientRect();
      return { dialogueBottom: dialogue.bottom, panelTop: panel.top };
    });
    expect(boxes.panelTop, `console below the dialogue at ${width}x${height}`).toBeGreaterThanOrEqual(boxes.dialogueBottom);
    const geo = await geometry(page);
    expectComposerIn(geo, width, height);
    expect(geo.horizontalOverflow, `no horizontal overflow at ${width}x${height}`).toBe(false);
  }
});

test("a guest with the banner and channel tabs keeps the composer in view at phone sizes", async ({ page }) => {
  const cases: [string, [number, number][]][] = [
    ["Tripartite Siege", [[390, 667], [320, 568]]], // two counterparts and two stakeholders: the channel tabs are on screen
    ["Restoring a school occupied by armed actors", [[320, 568]]], // two counterparts and five stakeholders: the long school title once pushed the composer off screen at 320
  ];
  for (const [card, sizes] of cases) {
    await page.goto("signin");
    await page.getByRole("button", { name: "Try it now, no account" }).click();
    await page.locator("a.cover-card").filter({ hasText: card }).click();
    await page.getByRole("button", { name: "Start" }).click();
    await page.getByRole("button", { name: "What we know", exact: true }).click();
    await page.getByRole("button", { name: "Objective", exact: true }).click();
    await page.getByRole("button", { name: "Enter Negotiation →" }).click();
    await page.getByLabel("Your message").waitFor();

    for (const [width, height] of sizes) {
      await page.setViewportSize({ width, height });
      await page.goto(page.url());
      await page.getByLabel("Your message").waitFor();
      await expect(page.getByRole("note")).toBeVisible(); // the guest banner is on screen
      await expect(page.locator(".interlocutor-channel-bar")).toBeVisible(); // and so are the channel tabs
      await expectFits(page, width, height);
    }
  }
});
