import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ME, renderAt, stubApi } from "../test-utils";
import { OrgPage } from "./Org";

const SESSION = {
  id: "s1",
  scenario_id: "c1",
  title: "Hostile checkpoint",
  cover: "checkpoint",
  mode: "solo",
  status: "active",
  turn: 3,
  result: null,
  created_at: "2026-09-30T10:00:00Z",
};

describe("OrgPage sessions", () => {
  it("shows no Watch link for the admin's own session, and one for another member's", async () => {
    stubApi({
      "GET org/members": [],
      "GET org/invites": [],
      "GET sessions?scope=org": [
        { ...SESSION, player: "Alice", player_id: ME.id },
        { ...SESSION, id: "s2", player: "Bob", player_id: "u2" },
      ],
    });
    renderAt("/org", <OrgPage />);
    const own = await screen.findByRole("row", { name: /Alice/ });
    expect(within(own).queryByRole("link", { name: "Watch" })).toBeNull();
    expect(within(own).getByRole("link", { name: "Continue" })).toHaveAttribute("href", "/play/s1");
    const other = screen.getByRole("row", { name: /Bob/ });
    expect(within(other).getByRole("link", { name: "Watch" })).toHaveAttribute("href", "/sessions/s2/watch");
  });
});
