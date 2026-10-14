import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router";
import { json, renderAt, stubApi } from "../test-utils";
import { Debrief } from "./Debrief";
import { Layout } from "./Layout";

const PENDING = { status: "pending", outcome: null, reached: [], debrief: null, scores: null, flags: [], dials: {} };

describe("Debrief", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("keeps polling after a transient failure and reaches ready", async () => {
    let count = 0;
    const fetchMock = stubApi({
      "GET sessions/s1/debrief": () =>
        ++count === 1
          ? json(PENDING)
          : count === 2
            ? json({ detail: "temporary" }, 503)
            : json({ ...PENDING, status: "ready", debrief: { summary: "ready" } }),
    });
    renderAt("/sessions/s1/debrief", <Debrief />, "/sessions/:id/debrief");
    await act(async () => {});
    expect(screen.getByText(/Writing your debrief/)).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000); // the 503 poll
    });
    expect(screen.getByRole("alert")).toHaveTextContent("temporary");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(screen.getByText("ready")).toBeInTheDocument();
    const debriefCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("sessions/s1/debrief"));
    expect(debriefCalls.length).toBe(3);
  });

  it("retries an initial transient failure and reaches ready", async () => {
    let count = 0;
    const fetchMock = stubApi({
      "GET sessions/s1/debrief": () =>
        ++count === 1
          ? json({ detail: "debrief service down" }, 503)
          : json({ ...PENDING, status: "ready", debrief: { summary: "ready" } }),
    });
    renderAt("/sessions/s1/debrief", <Debrief />, "/sessions/:id/debrief");
    await act(async () => {});
    expect(screen.getByRole("alert")).toHaveTextContent("debrief service down"); // visible while waiting
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(screen.getByText("ready")).toBeInTheDocument();
    const debriefCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("sessions/s1/debrief"));
    expect(debriefCalls.length).toBe(2); // one retry, then ready stops the polling
  });

  it("stops polling on a terminal error", async () => {
    let count = 0;
    const fetchMock = stubApi({
      "GET sessions/s1/debrief": () => (++count === 1 ? json(PENDING) : json({ detail: "gone" }, 410)),
    });
    renderAt("/sessions/s1/debrief", <Debrief />, "/sessions/:id/debrief");
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("gone");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000);
    });
    expect(fetchMock.mock.calls.length).toBe(2);
  });

  it.each(["ready", "failed"] as const)(
    "refreshes the header token allowance when the background debrief turns %s",
    async (terminal) => {
      let polls = 0;
      let allowanceCalls = 0;
      const fetchMock = stubApi({
        "GET sessions/s1/debrief": () =>
          ++polls === 1
            ? json(PENDING)
            : json(
                terminal === "ready"
                  ? { ...PENDING, status: "ready", debrief: { summary: "Debrief done." } }
                  : { ...PENDING, status: "failed" },
              ),
        "GET me/allowance": () => {
          allowanceCalls += 1;
          return json({ used_tokens: 90, limit_tokens: 100, remaining_percent: allowanceCalls > 1 ? 42 : 10, resets_at: "2026-10-12T00:00:00Z" });
        },
        "GET sessions/s1/coach/suggestions": { suggestions: [], citations: [] },
      });
      renderAt(
        "/sessions/s1/debrief",
        <Routes>
          <Route element={<Layout />}>
            <Route path="/sessions/:id/debrief" element={<Debrief />} />
          </Route>
        </Routes>,
        "/*",
      );
      await act(async () => {});
      expect(screen.getByText(/Writing your debrief/)).toBeInTheDocument();
      expect(screen.getByLabelText("10% of today's tokens left")).toBeInTheDocument(); // the header starts stale
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000); // the poll that finds the debrief settled
      });
      await act(async () => {});
      expect(screen.getByText(terminal === "ready" ? "Debrief done." : /could not be written/)).toBeInTheDocument();
      expect(screen.getByLabelText("42% of today's tokens left")).toBeInTheDocument(); // the completion refreshed it
      expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("me/allowance"))).toHaveLength(2);
    },
  );

  it("renders DebriefCoach with suggestions and allows asking questions", async () => {
    stubApi({
      "GET sessions/s1/debrief": { ...PENDING, status: "ready", debrief: { summary: "Session completed" } },
      "GET sessions/s1/coach/suggestions": {
        suggestions: ["Why did the counterpart resist?"],
        citations: [
          {
            id: "cchn-tool-09",
            title: "Analyzing the Position of the Counterpart (the Iceberg)",
            framework: "CCHN Field Manual",
            citation: "CCHN Field Manual (2019), Tool 9, pp. 199-217",
            summary: "WHAT, HOW and WHY of the position.",
          },
        ],
      },
    });
    renderAt("/sessions/s1/debrief", <Debrief />, "/sessions/:id/debrief");
    await act(async () => {});
    expect(screen.getByText("Ask the Coach")).toBeInTheDocument();
    expect(screen.getByText(/Why did the counterpart resist\?/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask Coach" })).toBeInTheDocument();
  });
});

describe("Debrief report", () => {
  const READY = {
    status: "ready",
    outcome: { id: "ended_by_trainee", label: "Session ended by the trainee", result: "ended", turn: 3 },
    reached: [{ id: "step", label: "First step agreed", result: "partial", turn: 2 }],
    debrief: {
      summary: "You asked well but stopped early.",
      strengths: ["Listened."],
      improvements: ["Ask more."],
      did_well: [{ turn: 2, note: "Proposed a concrete step.", quote: "could we start with the medical unit?" }],
      missed: [
        { turn: 8, note: "He opened a door.", quote: "anything else I can assist you with?", try_instead: "What is hardest for you?" },
      ],
      one_focus: { title: "Identify his interests", advice: "Ask open questions first." },
      score_check: [
        { id: "questioning", first: 4, second: 1, uncertain: true },
        { id: "interests", first: null, second: 3, uncertain: true },
      ],
    },
    scores: {
      scores: [
        { id: "questioning", score: 4, quote: "What worries you" },
        { id: "interests", score: null, quote: "" },
      ],
      flags: [],
    },
    flags: [{ turn: 4, id: "bypasses_authority", quote: "can you please approve this", text: "" }],
    dials: { trust: 18, tension: 45 },
    hidden_facts: [
      { id: "a", text: "He is ashamed of the overcrowding.", found: false, unlock: "trust at 50 or more" },
      { id: "b", text: "He would welcome medical support.", found: true, unlock: "" },
    ],
    dimensions: { questioning: "Quality of questioning", interests: "Identifying interests" },
    dial_causes: [
      { turn: 4, kind: "move", label: "bypasses authority", quote: "can you please approve this", changes: { trust: -12, tension: 10 } },
      { turn: 5, kind: "twist", label: "Ministry calls mid-meeting", quote: "", changes: { tension: 15 } },
    ],
  };

  it("lays the run out: outcome, skills, hidden facts, turn notes and one focus", async () => {
    stubApi({ "GET sessions/s1/debrief": READY, "GET sessions/s1/coach/suggestions": { suggestions: [], citations: [] } });
    renderAt("/sessions/s1/debrief", <Debrief />, "/sessions/:id/debrief");
    await screen.findByText("Session ended by the trainee");
    expect(screen.getByText("✓ First step agreed")).toBeInTheDocument();
    expect(screen.getByText("You asked well but stopped early.")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Quality of questioning" })).toHaveAttribute("aria-valuenow", "4");
    expect(screen.getByText("4/5")).toBeInTheDocument();
    expect(screen.getByText("Identifying interests")).toBeInTheDocument();
    expect(screen.getByText("Not observed")).toBeInTheDocument();
    expect(screen.getByText(/Two scoring passes gave 4 and 1 \(3 apart\)/)).toBeInTheDocument();
    expect(screen.getByText(/One scoring pass saw no evidence/)).toBeInTheDocument();
    expect(screen.getByText(/Hidden facts · 1 of 2 found/)).toBeInTheDocument();
    expect(screen.getByText("It would have come out when: trust at 50 or more.")).toBeInTheDocument(); // only for the missed one
    expect(screen.getAllByText(/It would have come out when/)).toHaveLength(1);
    expect(screen.getByText("Why the dials moved")).toBeInTheDocument();
    expect(screen.getByText("▼ Trust −12")).toBeInTheDocument();
    expect(screen.getByText("▲ Tension +10")).toBeInTheDocument();
    expect(screen.getByText(/bypasses authority ·/)).toHaveTextContent("bypasses authority · “can you please approve this”");
    expect(screen.getByText("Ministry calls mid-meeting")).toBeInTheDocument(); // a twist has no trainee quote
    expect(screen.getByText("Proposed a concrete step.")).toBeInTheDocument();
    expect(screen.getByText("“could we start with the medical unit?”")).toBeInTheDocument();
    expect(screen.getByText("Missed opportunity")).toBeInTheDocument();
    expect(screen.getByText("“What is hardest for you?”")).toBeInTheDocument();
    expect(screen.getByText("Identify his interests")).toBeInTheDocument();
    expect(screen.getByText("Ask open questions first.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rule flags" }).parentElement).toHaveTextContent("Turn 4 · Bypasses authority");
  });

  it("falls back to the plain strengths and improvements for a debrief without turn notes", async () => {
    const old = { ...READY, debrief: { summary: "Old.", strengths: ["Listened."], improvements: ["Ask more."] }, hidden_facts: [], dial_causes: [] };
    stubApi({ "GET sessions/s1/debrief": old, "GET sessions/s1/coach/suggestions": { suggestions: [], citations: [] } });
    renderAt("/sessions/s1/debrief", <Debrief />, "/sessions/:id/debrief");
    await screen.findByText("Old.");
    expect(screen.getByText("Listened.")).toBeInTheDocument();
    expect(screen.getByText("Ask more.")).toBeInTheDocument();
    expect(screen.queryByText("Missed opportunity")).not.toBeInTheDocument();
    expect(screen.queryByText(/Hidden facts/)).not.toBeInTheDocument();
    expect(screen.queryByText("Why the dials moved")).not.toBeInTheDocument();
  });
});
