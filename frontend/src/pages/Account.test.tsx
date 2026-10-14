import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { appUrl, nav } from "../api/client";
import { renderAt, stubApi } from "../test-utils";
import { Account } from "./Account";

describe("Account", () => {
  it("creates an organisation and opens its page", async () => {
    const to = vi.spyOn(nav, "to").mockImplementation(() => {});
    const fetchMock = stubApi({ "POST orgs": { id: "o2", name: "Field Trainers", role: "admin", personal: false } });
    renderAt("/account", <Account />);
    fireEvent.change(screen.getByLabelText("Organisation name"), { target: { value: "Field Trainers" } });
    fireEvent.click(screen.getByRole("button", { name: "Create organisation" }));
    await vi.waitFor(() => expect(to).toHaveBeenCalledWith(appUrl("org")));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(post?.[0])).toContain("/api/orgs");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ name: "Field Trainers" });
  });
});
