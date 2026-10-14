import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";
import type { S } from "./api/client";
import { MeContext } from "./me";

type Stub = unknown | ((init?: RequestInit) => Response);

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

/** A promise a test resolves by hand, for requests that must stay pending. */
export function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((r) => (resolve = r));
  return { promise, resolve };
}

export function events(...items: [string, unknown][]): Response {
  return new Response(items.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(""));
}

/** Replaces fetch. Keys are "METHOD path?query" with the path after /api/, e.g. "GET scenarios". */
export function stubApi(routes: Record<string, Stub>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const key = `${init?.method ?? "GET"} ${url.pathname.replace(/^\/api\//, "")}${url.search}`;
    const route = routes[key];
    if (route === undefined) return json({ detail: `no stub for ${key}` }, 404);
    return typeof route === "function" ? (route as (init?: RequestInit) => Response)(init) : json(route);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const PERSONAL = { id: "o1", name: "Alice", role: "admin" as const, personal: true };
export const ME: S["MeOut"] = {
  id: "u1",
  email: "alice@example.test",
  display_name: "Alice",
  is_superadmin: false,
  is_guest: false,
  active_org: PERSONAL,
  orgs: [PERSONAL],
};

export function renderAt(path: string, element: ReactNode, route = path, me: S["MeOut"] = ME) {
  return render(
    <MeContext.Provider value={me}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </MeContext.Provider>,
  );
}
