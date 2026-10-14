import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";
import { routes } from "../routes";
import { ME, stubApi } from "../test-utils";

/** The real route table, so removing a guard wrapper from routes.tsx fails these tests. */
function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe("route guards", () => {
  it("shows a personal-only user the message on /rules, no rule inputs, and no rules request", async () => {
    const fetchMock = stubApi({ "GET me": ME });
    renderRoute("/rules");
    expect(await screen.findByText("This page is for organisation admins.")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes("/api/rules"))).toBe(false);
  });

  it("serves /privacy to a visitor who is not signed in, without asking who they are", async () => {
    const fetchMock = stubApi({}); // no stubs: any request, /api/me included, would fail loudly
    renderRoute("/privacy");
    expect(await screen.findByRole("heading", { name: "Privacy notice" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes("/api/me"))).toBe(false);
  });

  it("keeps a non-superadmin off /usage", async () => {
    const fetchMock = stubApi({ "GET me": ME });
    renderRoute("/usage");
    expect(await screen.findByText("This page is for platform admins.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create" })).toBeNull();
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes("/api/admin/"))).toBe(false);
  });
});
