import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLoad } from "./hooks";
import { deferred, json } from "./test-utils";

describe("useLoad", () => {
  it("ignores a response for the old path that resolves after the new path's", async () => {
    let resolveOld!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).endsWith("/old")
          ? new Promise<Response>((resolve) => {
              resolveOld = resolve;
            })
          : Promise.resolve(json({ id: "new" })),
      ),
    );
    const { result, rerender } = renderHook(({ path }) => useLoad<{ id: string }>(path), { initialProps: { path: "old" } });
    rerender({ path: "new" });
    await waitFor(() => expect(result.current.data?.id).toBe("new"));
    await act(async () => {
      resolveOld(json({ id: "old" }));
    });
    expect(result.current.data?.id).toBe("new");
  });

  it("exposes no data while the path has changed but the response has not arrived", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ id: "x" }))));
    const { result, rerender } = renderHook(({ path }) => useLoad<{ id: string }>(path), { initialProps: { path: "a" } });
    await waitFor(() => expect(result.current.data?.id).toBe("x"));
    rerender({ path: "b" });
    expect(result.current.data).toBeUndefined();
  });

  it("ignores a reload captured for an old path so it cannot cancel the new path's load", async () => {
    const requests: ReturnType<typeof deferred>[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        const request = deferred();
        requests.push(request);
        return request.promise;
      }),
    );
    const { result, rerender } = renderHook(({ path }) => useLoad<{ id: string }>(path), { initialProps: { path: "a" } });
    await act(async () => requests[0].resolve(json({ id: "a" })));
    const staleReload = result.current.reload; // captured by a page action before the route changes
    rerender({ path: "b" });
    act(() => {
      void staleReload(); // the old page's action finishes after navigation and calls its captured reload
    });
    await act(async () => requests[1].resolve(json({ id: "b" })));
    expect(requests).toHaveLength(2); // the stale reload returned without taking over
    expect(result.current.data?.id).toBe("b");
  });

  it("fetches nothing when a captured reload is called after unmount", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json({ id: "x" })));
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useLoad<{ id: string }>("a"));
    await waitFor(() => expect(result.current.data?.id).toBe("x"));
    const staleReload = result.current.reload; // an action finishing after the page is gone
    unmount();
    await act(async () => {
      void staleReload();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
