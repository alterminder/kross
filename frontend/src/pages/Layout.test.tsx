import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { nav } from "../api/client";
import { ME, renderAt, stubApi } from "../test-utils";
import { Layout } from "./Layout";

const ALLOWANCE = { used_tokens: 90, limit_tokens: 100, remaining_percent: 10, resets_at: "2026-10-12T00:00:00Z" };

describe("Layout", () => {
  beforeEach(() => {
    stubApi({ "GET me/allowance": ALLOWANCE }); // the header's token bar; tests that stub their own fetch hide it
  });

  it("shows no org wording to a user whose only org is personal", () => {
    renderAt("/", <Layout />);
    expect(screen.queryByRole("button", { name: /Organisation:/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "Organisation" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Rules" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Usage" })).toBeNull();
  });

  it("gives an admin of a real org the switcher and the admin pages", () => {
    const org = { id: "o2", name: "Field office", role: "admin" as const, personal: false };
    renderAt("/", <Layout />, "/", { ...ME, active_org: org, orgs: [ME.orgs[0], org] });
    expect(screen.getByRole("button", { name: "Organisation: Field office" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Organisation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rules" })).toBeInTheDocument();
  });

  it("shows a member of a real org the switcher but not the admin pages", () => {
    const org = { id: "o2", name: "Field office", role: "member" as const, personal: false };
    renderAt("/", <Layout />, "/", { ...ME, active_org: org, orgs: [ME.orgs[0], org] });
    expect(screen.getByRole("button", { name: "Organisation: Field office" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Organisation" })).toBeNull();
  });

  it("switches organisation from the dropdown, the active one marked with aria-current", async () => {
    const user = userEvent.setup();
    const fetchMock = stubApi({ "POST orgs/active": () => new Response(null, { status: 204 }) });
    const redirect = vi.spyOn(nav, "to").mockImplementation(() => {});
    const org = { id: "o2", name: "Field office", role: "admin" as const, personal: false };
    renderAt("/", <Layout />, "/", { ...ME, orgs: [ME.orgs[0], org] });
    await user.click(screen.getByRole("button", { name: "Organisation: Personal" }));
    expect(screen.getByRole("button", { name: "Personal" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Field office Admin" })).not.toHaveAttribute("aria-current");
    await user.click(screen.getByRole("button", { name: "Field office Admin" }));
    await vi.waitFor(() => expect(redirect).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/orgs/active"),
      expect.objectContaining({ method: "POST", body: JSON.stringify({ org_id: "o2" }) }),
    );
  });

  it("choosing the active org only closes the popup", async () => {
    const user = userEvent.setup();
    const fetchMock = stubApi({});
    const org = { id: "o2", name: "Field office", role: "member" as const, personal: false };
    renderAt("/", <Layout />, "/", { ...ME, orgs: [ME.orgs[0], org] });
    await user.click(screen.getByRole("button", { name: "Organisation: Personal" }));
    await user.click(screen.getByRole("button", { name: "Personal" }));
    expect(screen.getByRole("button", { name: "Field office Member" })).not.toBeVisible();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0); // no org switch
  });

  it("closes the switcher with Escape, focus back on the toggle", async () => {
    const user = userEvent.setup();
    const org = { id: "o2", name: "Field office", role: "admin" as const, personal: false };
    renderAt("/", <Layout />, "/", { ...ME, orgs: [ME.orgs[0], org] });
    const toggle = screen.getByRole("button", { name: "Organisation: Personal" });
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Field office Admin" })).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Field office Admin" })).not.toBeVisible();
    expect(toggle).toHaveFocus();
  });

  it("gives a superadmin the usage page", () => {
    renderAt("/", <Layout />, "/", { ...ME, is_superadmin: true });
    expect(screen.getByRole("link", { name: "Usage" })).toBeInTheDocument();
  });

  it("tells a guest so, offers sign-in and hides the account and authoring controls", async () => {
    renderAt("/", <Layout />, "/", { ...ME, is_guest: true, email: null, display_name: "Guest" });
    expect(screen.getByRole("note")).toHaveTextContent("You are playing as a guest");
    expect(screen.getByRole("button", { name: "Leave" })).not.toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Profile menu" }));
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/signin");
    expect(screen.queryByRole("link", { name: "Guest" })).toBeNull(); // no account page for a guest
    expect(screen.queryByRole("link", { name: "My account" })).toBeNull();
    expect(screen.getByRole("button", { name: "Leave" })).toBeInTheDocument();
  });

  it("keeps account actions behind the profile button and dismisses them with Escape or an outside click", async () => {
    const user = userEvent.setup();
    renderAt("/", <Layout />);
    const profile = screen.getByRole("button", { name: "Profile menu" });
    expect(screen.getByRole("link", { name: "My account" })).not.toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).not.toBeVisible();
    await user.click(profile);
    expect(screen.getByRole("link", { name: "My account" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("link", { name: "My account" })).not.toBeVisible();
    expect(profile).toHaveFocus();
    await user.click(profile);
    await user.click(screen.getByRole("link", { name: "KROSS: back to the main page" }));
    expect(screen.getByRole("link", { name: "My account" })).not.toBeVisible();
  });

  it("signs out through the existing logout endpoint from the dropdown", async () => {
    const fetchMock = stubApi({ "POST auth/logout": () => new Response(null, { status: 204 }) });
    const redirect = vi.spyOn(nav, "to").mockImplementation(() => {});
    renderAt("/", <Layout />);
    await userEvent.click(screen.getByRole("button", { name: "Profile menu" }));
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/auth/logout"), expect.objectContaining({ method: "POST" }));
    expect(redirect).toHaveBeenCalledWith(expect.stringContaining("/signin"));
  });

  it("compacts the top bar when scrolled down and restores it at the top", () => {
    renderAt("/", <Layout />);
    const header = document.querySelector("header.topbar") as HTMLElement;
    expect(header.className).not.toContain("compact");
    act(() => {
      Object.defineProperty(window, "scrollY", { value: 100, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });
    expect(header.className).toContain("compact");
    act(() => {
      Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });
    expect(header.className).not.toContain("compact");
  });

  it("shows no guest notice to a signed-in user", () => {
    renderAt("/", <Layout />);
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("shows the daily token allowance, and unlimited is never shown as 0%", async () => {
    stubApi({ "GET me/allowance": { ...ALLOWANCE, limit_tokens: null, remaining_percent: null } });
    renderAt("/", <Layout />);
    expect(await screen.findByText("Daily limit: unlimited")).toBeInTheDocument();
    expect(screen.queryByText(/0%/)).toBeNull();
    expect(screen.queryByLabelText(/today's tokens left/)).toBeNull();
  });

  it("shows the percent left of today's tokens, rounded, and refetches after a model request settles", async () => {
    const fetchMock = stubApi({ "GET me/allowance": { ...ALLOWANCE, remaining_percent: 10.37 } });
    renderAt("/", <Layout />);
    const label = await screen.findByText(
      (_, element) => element?.parentElement?.className === "token-bar" && element.textContent === "10% left",
    ); // rounded, no raw float in the header
    expect(label).toBeInTheDocument();
    expect(screen.getByLabelText("10% of today's tokens left")).toHaveAttribute("value", "10.37"); // the meter keeps the real value
    act(() => {
      window.dispatchEvent(new Event("nlab:spent"));
    });
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("me/allowance")).length).toBeGreaterThan(1),
    );
  });
});
