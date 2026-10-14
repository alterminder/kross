import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deferred, json, stubApi } from "../test-utils";
import { lastChange, useProgress, type EngineEvent } from "./progress";

const ACTIVE = { session_id: "s1", status: "active", state: {}, turns: [] };

describe("useProgress: queued refreshes", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("a queued refresh does not run after the current request is terminal", async () => {
    let calls = 0;
    const pending = deferred();
    stubApi({
      "GET sessions/s1/progress": () =>
        ++calls === 1 ? json(ACTIVE) : calls === 2 ? pending.promise : json({ detail: "gone" }, 404),
    });
    const hook = renderHook(() => useProgress("s1"));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000); // this poll's request stays in flight
    });
    void hook.result.current.reload(); // an action queues a refresh behind it
    pending.resolve(json({ detail: "gone" }, 404));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(calls).toBe(2); // the 404 ends the run: no queued follow-up request
  });

  it("a queued refresh still runs after a transient network error", async () => {
    let calls = 0;
    let reject!: (error: Error) => void;
    stubApi({
      "GET sessions/s1/progress": () =>
        ++calls === 1
          ? json(ACTIVE)
          : calls === 2
            ? new Promise<Response>((_, r) => {
                reject = r;
              })
            : json(ACTIVE),
    });
    const hook = renderHook(() => useProgress("s1"));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    void hook.result.current.reload();
    reject(new Error("network"));
    await act(async () => {});
    expect(calls).toBe(3); // a transient failure does not strand the queued refresh
    expect(hook.result.current.error).toBeUndefined(); // the follow-up cleared it
  });
});

describe("lastChange", () => {
  const dial = (over: Partial<EngineEvent>): EngineEvent => ({ turn: 1, source: "move", kind: "dial", dial: "trust", before: 30, after: 18, ...over });

  it("names the trainee's own words for a move and the newest change wins", () => {
    const log = [dial({ ref: "evades_direct_question", quote: "later" }), dial({ turn: 2, ref: "bypasses_authority", quote: "can you please approve this" })];
    expect(lastChange(log, "trust")).toEqual({ delta: -12, why: "bypasses authority · “can you please approve this”" });
  });

  it("names silence, a twist and a manual override as what they were, and skips a change that moved nothing", () => {
    expect(lastChange([dial({ source: "auto", dial: "patience", before: 75, after: 67, reason: "Trainee silence / hesitation" })], "patience")).toEqual({
      delta: -8,
      why: "Trainee silence / hesitation",
    });
    expect(lastChange([dial({ source: "trainer", ref: "ministry_calls", before: 35, after: 50 })], "trust")).toEqual({ delta: 15, why: "twist: ministry calls" });
    expect(lastChange([dial({ source: "trainer", reason: "manual override", before: 50, after: 40 })], "trust")).toEqual({ delta: -10, why: "set by hand" });
    expect(lastChange([dial({ before: 50, after: 50 })], "trust")).toBeNull();
    expect(lastChange([dial({})], "tension")).toBeNull();
  });
});
