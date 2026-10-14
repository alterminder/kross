import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt, stubApi } from "../test-utils";
import { Library } from "./Library";

const CARD = {
  id: "c1",
  title: "Hostile checkpoint",
  cover: "checkpoint",
  visibility: "public",
  version: 1,
  submitted: false,
  difficulty: "intermediate",
  minutes: 20,
  skills: ["rapport", "firmness"],
  can_edit: false,
};

describe("Library", () => {
  it("shows each scenario as a card with its cover image, linking to the scenario", async () => {
    stubApi({ "GET scenarios": [CARD, { ...CARD, id: "c2", title: "My draft", cover: "school", visibility: "private" }], "GET sessions": [] });
    renderAt("/", <Library />);
    const card = await screen.findByRole("link", { name: /Hostile checkpoint/ });
    expect(card).toHaveAttribute("href", "/scenarios/c1");
    expect(card.style.backgroundImage).toContain("covers/checkpoint.webp");
    expect(within(card).getByText("Intermediate")).toBeInTheDocument();
    expect(within(card).getByText(/20 min/)).toBeInTheDocument();
    expect(within(card).queryByText("Private")).toBeNull();
    const draft = screen.getByRole("link", { name: /My draft/ });
    expect(draft.style.backgroundImage).toContain("covers/school.webp");
    expect(within(draft).getByText("Private")).toBeInTheDocument();
  });

  it("has no Scenarios heading and no New scenario link or button", async () => {
    stubApi({ "GET scenarios": [CARD], "GET sessions": [] });
    renderAt("/", <Library />);
    await screen.findByRole("link", { name: /Hostile checkpoint/ });
    expect(screen.queryByRole("heading", { name: "Scenarios" })).toBeNull();
    expect(screen.queryByRole("link", { name: "New scenario" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New scenario" })).toBeNull();
  });

  it("ends the grid with an Add scenario card linking to /scenarios/new", async () => {
    stubApi({ "GET scenarios": [CARD], "GET sessions": [] });
    renderAt("/", <Library />);
    await screen.findByRole("link", { name: /Hostile checkpoint/ });
    const grid = document.querySelector(".cards") as HTMLElement;
    const links = within(grid).getAllByRole("link");
    const last = links[links.length - 1];
    expect(last).toHaveAccessibleName("Add scenario");
    expect(last).toHaveAttribute("href", "/scenarios/new");
    expect(grid.lastElementChild).toBe(last);
  });

  it("uses the painted cover image only when the scenario chose it", async () => {
    stubApi({
      "GET scenarios": [
        { ...CARD, cover: "custom", cover_image_version: "v2" },
        { ...CARD, id: "c2", title: "Theme kept", cover: "camp", cover_image_version: "v2" },
      ],
      "GET sessions": [],
    });
    renderAt("/", <Library />);
    const painted = await screen.findByRole("link", { name: /Hostile checkpoint/ });
    expect(painted.style.backgroundImage).toContain("api/scenarios/c1/cover-image?v=v2");
    const themed = await screen.findByRole("link", { name: /Theme kept/ });
    expect(themed.style.backgroundImage).toContain("covers/camp.webp");
  });

  it("shows difficulty dots and keeps the skills tags in the DOM", async () => {
    stubApi({
      "GET scenarios": [
        CARD,
        { ...CARD, id: "c2", title: "Expert dive", difficulty: "expert", minutes: null },
        { ...CARD, id: "c3", title: "No level", difficulty: null },
        { ...CARD, id: "c4", title: "Odd level", difficulty: "hard" },
      ],
      "GET sessions": [],
    });
    renderAt("/", <Library />);
    const mid = await screen.findByRole("link", { name: /Hostile checkpoint/ });
    const dots = within(mid).getByRole("img", { name: "Difficulty: intermediate, 2 of 4" });
    expect(dots.querySelectorAll("[data-filled]")).toHaveLength(2);
    expect(within(mid).getByText("rapport")).toBeInTheDocument();
    expect(within(mid).getByText("firmness")).toBeInTheDocument();
    const expert = screen.getByRole("link", { name: /Expert dive/ });
    expect(expert.querySelectorAll("[data-filled]")).toHaveLength(4);
    const none = screen.getByRole("link", { name: /No level/ });
    expect(none.querySelector(".diff-dots")).toBeNull();
    const odd = screen.getByRole("link", { name: /Odd level/ });
    expect(odd.querySelector(".diff-dots")).toBeNull();
  });

  it("lists the user's sessions with a way back into each", async () => {
    stubApi({
      "GET scenarios": [CARD],
      "GET sessions": [
        { id: "s1", scenario_id: "c1", title: "Hostile checkpoint", cover: "checkpoint", mode: "solo", status: "active", turn: 3, result: null, player: null, created_at: "2026-09-30T10:00:00Z" },
        { id: "s2", scenario_id: "c1", title: "Hostile checkpoint", cover: "checkpoint", mode: "solo", status: "ended", turn: 7, result: "success", player: null, created_at: "2026-09-29T10:00:00Z" },
        { id: "s3", scenario_id: "c1", title: "Painted run", cover: "custom", cover_image_version: "v7", mode: "solo", status: "ended", turn: 2, result: "partial", player: null, created_at: "2026-09-28T10:00:00Z" },
        { id: "s4", scenario_id: "c1", title: "Custom without image", cover: "custom", mode: "solo", status: "ended", turn: 1, result: null, player: null, created_at: "2026-09-27T10:00:00Z" },
      ],
    });
    renderAt("/", <Library />);
    expect(await screen.findByRole("link", { name: "Continue" })).toHaveAttribute("href", "/play/s1");
    expect(screen.getAllByRole("link", { name: "Debrief" })[0]).toHaveAttribute("href", "/sessions/s2/debrief");
    // a painted scenario's session uses the painting; one without an image falls back to the field theme,
    // and /covers/custom.webp is never requested
    expect(screen.getByText("Painted run").closest("li")!.querySelector("img")!.src).toContain("scenarios/c1/cover-image?v=v7");
    expect(screen.getByText("Custom without image").closest("li")!.querySelector("img")!.src).toContain("covers/field.webp");
    expect(document.querySelectorAll('img[src*="custom.webp"]')).toHaveLength(0);
  });
});
