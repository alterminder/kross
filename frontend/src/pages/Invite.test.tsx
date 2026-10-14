import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { nav } from "../api/client";
import { renderAt, stubApi } from "../test-utils";
import { Invite } from "./Invite";

describe("Invite", () => {
  it("shows the admin-visibility notice and joins only after it is acknowledged", async () => {
    const to = vi.spyOn(nav, "to").mockImplementation(() => {});
    const fetchMock = stubApi({
      "POST invites/preview": { org_name: "Field office", role: "member", notice: "Admins of Field office can watch your sessions.", problem: null, already_member: false },
      "POST invites/accept": { org_id: "o2", org_name: "Field office" },
      "POST orgs/active": () => new Response(null, { status: 204 }),
    });
    renderAt("/invite#tok123", <Invite />, "/invite");
    expect(await screen.findByText("Admins of Field office can watch your sessions.")).toBeInTheDocument();
    const join = screen.getByRole("button", { name: /Join/ });
    expect(join).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I have read this"));
    await userEvent.click(join);
    await vi.waitFor(() => expect(to).toHaveBeenCalled());
    const accept = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/invites/accept"));
    expect(JSON.parse(String(accept?.[1]?.body))).toEqual({ token: "tok123", acknowledged: true });
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("tok123"))).toBe(true); // never in a URL
  });

  it("explains an expired link", async () => {
    stubApi({ "POST invites/preview": { org_name: "Field office", role: "member", notice: "", problem: "expired", already_member: false } });
    renderAt("/invite#tok123", <Invite />, "/invite");
    expect(await screen.findByText(/has expired/)).toBeInTheDocument();
  });
});
