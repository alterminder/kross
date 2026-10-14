import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { nav } from "../api/client";
import { json, stubApi } from "../test-utils";
import { SignIn } from "./SignIn";

const PROVIDERS = [{ name: "google", label: "Google" }];

function renderSignIn() {
  return render(
    <MemoryRouter>
      <SignIn />
    </MemoryRouter>,
  );
}

describe("SignIn", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers no guest button when the deployment has guest play off", async () => {
    stubApi({ "GET auth/providers": PROVIDERS, "GET auth/guest": { enabled: false } });
    renderSignIn();
    await screen.findByRole("link", { name: "Sign in with Google" });
    expect(screen.queryByRole("button", { name: /no account/ })).toBeNull();
  });

  it("links to the privacy notice", async () => {
    stubApi({ "GET auth/providers": PROVIDERS, "GET auth/guest": { enabled: false } });
    renderSignIn();
    expect(await screen.findByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
  });

  it("hides the dev sign-in from the choices", async () => {
    stubApi({ "GET auth/providers": [...PROVIDERS, { name: "dev", label: "Dev" }], "GET auth/guest": { enabled: false } });
    renderSignIn();
    await screen.findByRole("link", { name: "Sign in with Google" });
    expect(screen.queryByRole("link", { name: "Sign in with Dev" })).toBeNull();
  });

  it("a dev-only server is not reported as having no sign-in provider", async () => {
    stubApi({ "GET auth/providers": [{ name: "dev", label: "Dev" }], "GET auth/guest": { enabled: false } });
    renderSignIn();
    await screen.findByRole("link", { name: "Privacy" });
    await vi.waitFor(() => expect(screen.queryByText(/No sign-in provider/)).toBeNull());
  });

  it("shows the Google mark instead of the word, keeping the sign-in name", async () => {
    stubApi({ "GET auth/providers": PROVIDERS, "GET auth/guest": { enabled: false } });
    renderSignIn();
    const link = await screen.findByRole("link", { name: "Sign in with Google" });
    expect(link.querySelector("svg")).not.toBeNull();
    expect(link.textContent).toBe("Sign in with "); // only the word Google is replaced by the white mark
  });

  it("starts a guest in one click and opens the library", async () => {
    const go = vi.spyOn(nav, "to").mockImplementation(() => {});
    const fetchMock = stubApi({
      "GET auth/providers": PROVIDERS,
      "GET auth/guest": { enabled: true },
      "POST auth/guest": () => new Response(null, { status: 204 }),
    });
    renderSignIn();
    fireEvent.click(await screen.findByRole("button", { name: "Try it now, no account" }));
    await vi.waitFor(() => expect(go).toHaveBeenCalled());
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("says why when today's guest places are used up, and stays on the page", async () => {
    const go = vi.spyOn(nav, "to").mockImplementation(() => {});
    stubApi({
      "GET auth/providers": PROVIDERS,
      "GET auth/guest": { enabled: true },
      "POST auth/guest": () => json({ detail: "Guest practice is full for today. Sign in, or come back after 00:00 UTC." }, 429),
    });
    renderSignIn();
    fireEvent.click(await screen.findByRole("button", { name: "Try it now, no account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Guest practice is full for today");
    expect(go).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Try it now, no account" })).toBeEnabled();
  });
});
