import { describe, expect, it, vi } from "vitest";
import { json, stubApi } from "../test-utils";
import { api, nav } from "./client";

describe("api", () => {
  it("sends the CSRF header and a JSON body", async () => {
    const fetchMock = stubApi({ "POST sessions": { id: "s1" } });
    expect(await api("sessions", { method: "POST", body: { scenario_id: "x" } })).toEqual({ id: "s1" });
    const init = fetchMock.mock.calls[0][1];
    expect(new Headers(init?.headers).get("X-Requested-With")).toBe("nlab");
    expect(init?.body).toBe('{"scenario_id":"x"}');
    expect(init?.credentials).toBe("same-origin");
  });

  it("joins a list of issues into one message", async () => {
    stubApi({ "POST scenarios": () => json({ detail: [{ path: "title", message: "required" }, { msg: "bad" }] }, 422) });
    await expect(api("scenarios", { method: "POST", body: {} })).rejects.toMatchObject({
      status: 422,
      message: "required; bad",
    });
  });

  it("returns nothing for 204", async () => {
    stubApi({ "POST auth/logout": () => new Response(null, { status: 204 }) });
    expect(await api("auth/logout", { method: "POST" })).toBeUndefined();
  });

  it("sends the browser to the sign-in page on 401", async () => {
    const to = vi.spyOn(nav, "to").mockImplementation(() => {});
    stubApi({ "GET me": () => json({ detail: "Sign in first" }, 401) });
    await expect(api("me")).rejects.toMatchObject({ status: 401, message: "Sign in first" });
    expect(to).toHaveBeenCalledWith(new URL("signin", document.baseURI).href);
  });
});
