import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { S } from "../api/client";
import { json, renderAt, stubApi, deferred } from "../test-utils";
import { Watch } from "./Watch";

const PROGRESS: S["ProgressOut"] = {
  session_id: "s1",
  player: "Alice",
  status: "active",
  title: "Hostile checkpoint",
  counterpart: "Checkpoint commander",
  turn_running: false,
  injects_allowed: true,
  on_timeout: "guide",
  state: {
    turn: 1,
    dials: { trust: 40, hostility: 20 },
    level: "calm",
    outcome: null,
    offered: null,
    reached: [],
    moves: [{ turn: 1, id: "shows_respect", quote: "I hear you" }],
    injections: [],
    flags: [],
  },
  turns: [
    { number: 0, trainee_text: null, reply_text: "Stop there.", dials: { trust: 35, hostility: 20 }, events: [], scores: null, counterpart_request: null },
    {
      number: 1,
      trainee_text: "I hear you.",
      reply_text: "Good. What do you need?",
      dials: { trust: 40, hostility: 20 },
      events: [{ turn: 1, source: "move", kind: "dial", dial: "trust", before: 35, after: 40, ref: "shows_respect", quote: "I hear you", reason: "" }],
      scores: null,
      counterpart_request: null,
    },
  ],
  injections: [{ id: "shots_heard", label: "Shots are heard" }],
  outcomes: [{ id: "passage", label: "Convoy passage agreed", result: "success", when: { trust_gte: 65, rigidity_lte: 50 } }],
  comments: [],
};

const SESSION_OUT = { id: "s1", status: "ended", outcome: { result: "fail", label: "Time ran out without an agreement" } };

function progress(changes: object = {}) {
  return { ...PROGRESS, ...changes };
}

function at() {
  return renderAt("/sessions/s1/watch", <Watch />, "/sessions/:id/watch");
}

describe("Watch: live session", () => {
  it("shows the transcript as chat bubbles and one slider per dial", async () => {
    stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();
    expect(await screen.findByText("Stop there.")).toBeInTheDocument();
    expect(screen.getByText("I hear you.")).toBeInTheDocument();
    const trust = screen.getByRole("slider", { name: /trust/ });
    expect(trust).toHaveValue("40");
    expect(screen.getByRole("slider", { name: /hostility/ })).toHaveValue("20");
  });

  it("releasing a slider POSTs /dials once, with the final value, and shows the returned value", async () => {
    let trust = 40;
    const fetchMock = stubApi({
      "GET sessions/s1/progress": () => json(progress({ state: { ...PROGRESS.state, dials: { trust, hostility: 20 } } })),
      "POST sessions/s1/dials": (init?: RequestInit) => {
        trust = (JSON.parse(String(init?.body)) as { value: number }).value;
        return json(progress({ state: { ...PROGRESS.state, dials: { trust, hostility: 20 } } }));
      },
    });
    at();
    const slider = await screen.findByRole("slider", { name: /trust/ });
    fireEvent.change(slider, { target: { value: "65" } });
    fireEvent.pointerUp(slider);
    await waitFor(() => expect(slider).toHaveValue("65"));
    const posts = fetchMock.mock.calls.filter(([, init]) => String(init?.method) === "POST");
    expect(posts.length).toBe(1);
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ dial: "trust", value: 65 });
  });

  it("follows the server after a successful slider commit overtaken by a later update", async () => {
    let after = false;
    stubApi({
      "GET sessions/s1/progress": () =>
        json(after ? progress({ state: { ...PROGRESS.state, dials: { trust: 70, hostility: 20 } } }) : PROGRESS),
      "POST sessions/s1/dials": () => {
        after = true; // the POST writes 65; a later server value is already 70 when the reload lands
        return json(progress({ state: { ...PROGRESS.state, dials: { trust: 65, hostility: 20 } } }));
      },
    });
    at();
    const slider = await screen.findByRole("slider", { name: /trust/ });
    fireEvent.change(slider, { target: { value: "65" } });
    fireEvent.pointerUp(slider);
    await waitFor(() => expect(slider).toHaveValue("70")); // the draft ends with the commit, not at an exact match
  });

  it("a 409 says a turn is running and restores the slider to the server's value", async () => {
    stubApi({
      "GET sessions/s1/progress": PROGRESS,
      "POST sessions/s1/dials": () => json({ detail: "A turn is still running" }, 409),
    });
    at();
    const trust = await screen.findByRole("slider", { name: /trust/ });
    fireEvent.change(trust, { target: { value: "90" } });
    fireEvent.pointerUp(trust);
    expect(await screen.findByRole("alert")).toHaveTextContent("A turn is running; try again in a moment");
    await waitFor(() => expect(trust).toHaveValue("40")); // the server's value, not the draft
  });

  it("a preset twist POSTs /inject", async () => {
    const fetchMock = stubApi({
      "GET sessions/s1/progress": PROGRESS,
      "POST sessions/s1/inject": PROGRESS,
    });
    at();
    fireEvent.click(await screen.findByRole("button", { name: "Shots are heard" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => String(url).includes("/inject") && init?.method === "POST")).toBe(true),
    );
    const body = JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url).includes("/inject"))?.[1]?.body));
    expect(body).toEqual({ injection_id: "shots_heard" });
  });

  it("disables twists in a stage that forbids them, and says which stage", async () => {
    const fetchMock = stubApi({
      "GET sessions/s1/progress": progress({ injects_allowed: false, phase_label: "Formalities" }),
    });
    at();
    expect(await screen.findByRole("button", { name: "Shots are heard" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send twist" })).toBeDisabled();
    expect(screen.getByText(/The Formalities stage does not allow twists/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  it("asks the trainer how the meeting ends once the time is up, and POSTs the decision", async () => {
    const ended = progress({ on_timeout: "trainer", seconds_left: 0 });
    const fetchMock = stubApi({
      "GET sessions/s1/progress": ended,
      "POST sessions/s1/time-decision": { ...SESSION_OUT },
    });
    at();
    const card = await screen.findByRole("alertdialog", { name: "Time is up" });
    expect(card).toHaveTextContent("How does this meeting end?");
    fireEvent.click(screen.getByRole("button", { name: "End as a failure" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/time-decision"))).toBe(true));
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/time-decision"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ result: "fail" });
  });

  it("does not ask while there is time left, or when the scenario does not leave the end to the trainer", async () => {
    stubApi({ "GET sessions/s1/progress": progress({ on_timeout: "trainer", seconds_left: 300 }) });
    const first = at();
    await screen.findByRole("slider", { name: /trust/ });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    first.unmount();
    stubApi({ "GET sessions/s1/progress": progress({ on_timeout: "end", seconds_left: 0 }) });
    at();
    await screen.findByRole("slider", { name: /trust/ });
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("lets the trainer put the question off with Not yet", async () => {
    stubApi({ "GET sessions/s1/progress": progress({ on_timeout: "trainer", seconds_left: 0 }) });
    at();
    fireEvent.click(await screen.findByRole("button", { name: "Not yet" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("a preset twist is disabled once fired, and when the session has ended", async () => {
    stubApi({
      "GET sessions/s1/progress": progress({
        state: { ...PROGRESS.state, injections: [{ id: "shots_heard", label: "Shots are heard", source: "trainer", turn: 1 }] },
      }),
    });
    at();
    expect(await screen.findByRole("button", { name: "Shots are heard" })).toBeDisabled();
  });

  it("steering is disabled when the session has ended", async () => {
    stubApi({ "GET sessions/s1/progress": progress({ status: "ended" }) });
    at();
    expect(await screen.findByRole("button", { name: "Shots are heard" })).toBeDisabled();
    expect(screen.getByRole("slider", { name: /trust/ })).toBeDisabled();
  });

  it("a free-text twist POSTs /twists, shows the rewritten instruction, and shows a bias flag", async () => {
    const record = {
      id: "free_1",
      label: "Trainer twist",
      source: "trainer",
      turn: 1,
      original: "The river is rising",
      rewritten: "News arrives: the river is rising.",
      bias: { flagged: true, reason: "plays on a stereotype" },
    };
    stubApi({
      "GET sessions/s1/progress": PROGRESS,
      "POST sessions/s1/twists": progress({ state: { ...PROGRESS.state, injections: [record] } }),
    });
    at();
    fireEvent.change(await screen.findByLabelText("Free-text twist"), { target: { value: "The river is rising" } });
    fireEvent.click(screen.getByRole("button", { name: "Send twist" }));
    expect(await screen.findByText("Director: News arrives: the river is rising.")).toBeInTheDocument();
    expect(screen.getByText("Bias check: plays on a stereotype")).toBeInTheDocument();
  });

  it("lists the last turn's moves with quotes and dial changes in Rules fired", async () => {
    stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();
    const fired = (await screen.findByText("Rules fired · turn 1")).closest("section")!;
    expect(within(fired).getByText("shows respect")).toBeInTheDocument();
    expect(within(fired).getByText("trust +5")).toBeInTheDocument();
    expect(within(fired).getByText("“I hear you”")).toBeInTheDocument();
  });

  it("marks goal checks ✓, ✗ and · as the POC's goal panel does", async () => {
    stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();
    const goal = (await screen.findByText("Goal progress")).closest("section")!;
    expect(within(goal).getByText("✗ trust ≥ 65 (now 40)")).toBeInTheDocument();
    expect(within(goal).getByText("· rigidity ≤ 50 (now ?)")).toBeInTheDocument();
  });

  it("says the counterpart is thinking while a turn runs", async () => {
    stubApi({ "GET sessions/s1/progress": progress({ turn_running: true }) });
    at();
    expect(await screen.findByText(/Counterpart is thinking/)).toBeInTheDocument();
  });

  it("shows the pending, failed and unavailable debrief messages", async () => {
    const cases = [
      ["pending", /Writing the debrief/],
      ["failed", /could not be written/],
      ["unavailable", /No language model is configured/],
    ] as const;
    for (const [status, text] of cases) {
      stubApi({
        "GET sessions/s1/progress": ENDED,
        "GET sessions/s1/debrief": { status, outcome: null, reached: [], debrief: null, scores: null, flags: [], dials: {} },
      });
      at();
      fireEvent.click(await screen.findByRole("tab", { name: "Debrief" }));
      expect(await screen.findByText(text)).toBeInTheDocument();
      cleanup();
    }
  });
});

const ENDED = progress({
  status: "ended",
  state: {
    ...PROGRESS.state,
    outcome: { id: "passage", label: "Convoy passage agreed", result: "success", turn: 1 },
    reached: [{ id: "inspection", label: "Visual inspection agreed", result: "partial", turn: 1 }],
  },
  turns: [
    { number: 0, trainee_text: null, reply_text: "Stop there.", dials: { trust: 35, hostility: 20 }, events: [], scores: null, counterpart_request: null },
    {
      number: 1,
      trainee_text: "I hear you.",
      reply_text: "You may pass.",
      dials: { trust: 70, hostility: 15 },
      events: [{ turn: 1, source: "move", kind: "dial", dial: "trust", before: 35, after: 70, ref: "shows_respect", quote: "I hear you", reason: "" }],
      scores: { scores: [{ id: "rapport", score: 4, quote: "I hear you" }], flags: [] },
      counterpart_request: {
        role: "counterpart",
        model: "test-model",
        temperature: 0.7,
        messages: [
          { role: "system", content: "Play the counterpart. {\"dials\": {\"trust\": 70}}" },
          { role: "user", content: "I hear you." },
        ],
      },
    },
  ],
});

describe("Watch: debrief", () => {
  it("shows the summary card, the chart, the written debrief and the turn review", async () => {
    stubApi({
      "GET sessions/s1/progress": ENDED,
      "GET sessions/s1/debrief": {
        status: "ready",
        outcome: ENDED.state.outcome,
        reached: [],
        debrief: { summary: "Well held.", strengths: ["Listened."], improvements: ["Ask more."] },
        scores: null,
        flags: [],
        dials: { trust: 70 },
      },
    });
    at();
    fireEvent.click(await screen.findByRole("tab", { name: "Debrief" }));
    const summary = (await screen.findByText("Session summary")).closest("section")!;
    expect(summary).toHaveTextContent("Outcome: Convoy passage agreed — SUCCESS (turn 1)");
    expect(summary).toHaveTextContent("Milestone: Visual inspection agreed (turn 1)");
    expect(screen.getByText("Dials over time")).toBeInTheDocument();
    expect(screen.getByText("Turn 1 of 1")).toBeInTheDocument();
    expect(await screen.findByText("Well held.")).toBeInTheDocument();
  });

  it("charts trainer overrides appended after the saved turn snapshot", async () => {
    const { dialRows } = await import("../trainer/DialChart");
    const { viewOf } = await import("../trainer/progress");
    const data = progress({
      state: { ...PROGRESS.state, dials: { trust: 80, hostility: 20 } },
      turns: [
        PROGRESS.turns[0],
        {
          ...PROGRESS.turns[1],
          events: [
            ...PROGRESS.turns[1].events,
            { turn: 1, source: "trainer", kind: "dial", dial: "trust", before: 40, after: 80 }, // lands after the snapshot
          ],
        },
      ],
    });
    expect(dialRows(viewOf(data)).at(-1)?.trust).toBe(80); // the snapshot's 40 is not the turn's last value
  });

  it("says in progress while the session runs", async () => {
    stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();
    fireEvent.click(await screen.findByRole("tab", { name: "Debrief" }));
    expect(await screen.findByText(/In progress, turn 1/)).toBeInTheDocument();
  });

  it("the turn slider changes which turn's messages, rules and scores show", async () => {
    stubApi({ "GET sessions/s1/progress": ENDED });
    at();
    fireEvent.click(await screen.findByRole("tab", { name: "Debrief" }));
    const slider = await screen.findByRole("slider", { name: "Turn to review" });
    expect(screen.getByText("You may pass.")).toBeInTheDocument(); // turn 1's reply, selected by default
    expect(screen.getByText("rapport")).toBeInTheDocument();
    fireEvent.change(slider, { target: { value: "0" } });
    expect(screen.getByText("Turn 0 of 1")).toBeInTheDocument();
    expect(screen.getByText("Stop there.")).toBeInTheDocument(); // the opening line
    expect(screen.queryByText("rapport")).toBeNull(); // no scores made up to turn 0
    expect(screen.getByText("No rule fired on turn 0.")).toBeInTheDocument();
  });

  it("adding a comment POSTs /comments and shows it", async () => {
    const comments: object[] = [];
    const fetchMock = stubApi({
      "GET sessions/s1/progress": () => json({ ...ENDED, comments }),
      "POST sessions/s1/comments": (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body)) as { turn: number; text: string };
        comments.push({ ...body, author: "Grace", created_at: "2026-10-01T10:00:00Z" });
        return json({ ...body, author: "Grace", created_at: "2026-10-01T10:00:00Z" }, 201);
      },
    });
    at();
    fireEvent.click(await screen.findByRole("tab", { name: "Debrief" }));
    fireEvent.change(await screen.findByLabelText("Add review comment"), { target: { value: "Good opener" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("Good opener")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([url, init]) => String(url).includes("/comments") && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ turn: 1, text: "Good opener" });
  });

  it("shows the frozen counterpart request for the selected turn when opened", async () => {
    stubApi({ "GET sessions/s1/progress": ENDED });
    at();
    fireEvent.click(await screen.findByRole("tab", { name: "Debrief" }));
    fireEvent.click(await screen.findByText("What the counterpart model was sent"));
    expect(await screen.findByText("model test-model · temperature 0.7")).toBeInTheDocument();
    const promptCard = screen.getByText("What the counterpart model was sent").closest("section")!;
    expect(within(promptCard).getByText("I hear you.")).toBeInTheDocument(); // the user message, verbatim
  });
});

describe("Watch: overlapping drags", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("a poll matching a newer drag cannot let an older release end that drag", async () => {
    let trust = 40;
    const post = deferred();
    stubApi({
      "GET sessions/s1/progress": () => json(progress({ state: { ...PROGRESS.state, dials: { trust } } })),
      "POST sessions/s1/dials": () => post.promise,
    });
    at();
    await act(async () => {});
    const slider = screen.getByRole("slider", { name: /trust/ });
    fireEvent.change(slider, { target: { value: "65" } });
    fireEvent.pointerUp(slider); // the release's POST stays in flight
    await act(async () => {});
    fireEvent.change(slider, { target: { value: "75" } }); // a newer drag, still held
    trust = 75; // a legitimate server update lands before the first release's reload
    post.resolve(json(PROGRESS));
    await act(async () => {});
    expect(slider).toHaveValue("75");
    trust = 80;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000); // the next poll must not move the held slider
    });
    expect(slider).toHaveValue("75");
  });

  it("a no-op release back at the server's value clears its own draft", async () => {
    let trust = 40;
    const post = deferred();
    const fetchMock = stubApi({
      "GET sessions/s1/progress": () => json(progress({ state: { ...PROGRESS.state, dials: { trust } } })),
      "POST sessions/s1/dials": () => post.promise,
    });
    at();
    await act(async () => {});
    const slider = screen.getByRole("slider", { name: /trust/ });
    fireEvent.change(slider, { target: { value: "65" } });
    fireEvent.pointerUp(slider); // the release's POST stays in flight
    await act(async () => {});
    fireEvent.change(slider, { target: { value: "40" } });
    fireEvent.pointerUp(slider); // back at the server's value: nothing to send, the drag is over
    await act(async () => {});
    trust = 65;
    post.resolve(json(PROGRESS));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(slider).toHaveValue("65"); // the stale draft is gone: polls show through
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
  });
});

describe("Watch: polling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stops polling after a terminal error", async () => {
    let count = 0;
    const fetchMock = stubApi({
      "GET sessions/s1/progress": () => (++count === 1 ? json(PROGRESS) : json({ detail: "No such session" }, 404)),
    });
    at();
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000); // this poll gets the 404
    });
    expect(screen.getByRole("alert")).toHaveTextContent("No such session");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(fetchMock.mock.calls.length).toBe(2);
  });

  it("keeps polling every 2 seconds while the session is active", async () => {
    const fetchMock = stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4400);
    });
    expect(fetchMock.mock.calls.length).toBe(3);
  });

  it("applies a terminal response even when every request takes longer than the interval", async () => {
    let count = 0;
    const fetchMock = stubApi({
      "GET sessions/s1/progress": () =>
        ++count === 1
          ? json(PROGRESS)
          : new Promise<Response>((resolve) => setTimeout(() => resolve(json({ detail: "gone" }, 404)), 3000)),
    });
    at();
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000); // slow polls must not overlap and discard each other's terminal 404
    });
    expect(screen.getByRole("alert")).toHaveTextContent("gone");
    const stopped = fetchMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(fetchMock.mock.calls.length).toBe(stopped);
  });

  it("reloads a pending debrief every 3 seconds, stops on ready, and refreshes progress once", async () => {
    let debriefs = 0;
    let progresses = 0;
    stubApi({
      "GET sessions/s1/progress": () => {
        progresses += 1;
        return json(ENDED);
      },
      "GET sessions/s1/debrief": () => {
        debriefs += 1;
        return json({
          status: debriefs === 1 ? "pending" : "ready",
          outcome: null,
          reached: [],
          debrief: debriefs === 1 ? null : { summary: "Ready feedback", strengths: [], improvements: [] },
          scores: null,
          flags: [],
          dials: {},
        });
      },
    });
    at();
    await act(async () => {});
    fireEvent.click(screen.getByRole("tab", { name: "Debrief" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000);
    });
    expect(debriefs).toBe(2); // one reload while pending, then the polling stops on ready
    expect(screen.getByText("Ready feedback")).toBeInTheDocument();
    expect(progresses).toBe(2); // the ready debrief refreshes progress once, so the final scores appear
  });

  it("retries an initial transient debrief failure and shows the error while waiting", async () => {
    let calls = 0;
    stubApi({
      "GET sessions/s1/progress": ENDED,
      "GET sessions/s1/debrief": () =>
        ++calls === 1
          ? json({ detail: "debrief service down" }, 503)
          : json({
              status: "ready",
              outcome: null,
              reached: [],
              debrief: { summary: "Recovered feedback", strengths: [], improvements: [] },
              scores: null,
              flags: [],
              dials: {},
            }),
    });
    at();
    await act(async () => {});
    fireEvent.click(screen.getByRole("tab", { name: "Debrief" }));
    expect(screen.getByRole("alert")).toHaveTextContent("debrief service down"); // visible while waiting
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000); // the retry
    });
    expect(calls).toBe(2);
    expect(screen.getByText("Recovered feedback")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000);
    });
    expect(calls).toBe(2); // ready: polling stops
  });

  it("does not retry an initial terminal debrief failure", async () => {
    let calls = 0;
    stubApi({
      "GET sessions/s1/progress": ENDED,
      "GET sessions/s1/debrief": () => {
        calls += 1;
        return json({ detail: "gone" }, 404);
      },
    });
    at();
    await act(async () => {});
    fireEvent.click(screen.getByRole("tab", { name: "Debrief" }));
    expect(screen.getByRole("alert")).toHaveTextContent("gone");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000);
    });
    expect(calls).toBe(1);
  });

  it("refreshes the final scores once when the debrief fails, then stops", async () => {
    let debriefs = 0;
    let progresses = 0;
    stubApi({
      "GET sessions/s1/progress": () => {
        progresses += 1;
        return json(progresses === 1 ? progress({ status: "ended" }) : ENDED); // the refresh carries the late scores
      },
      "GET sessions/s1/debrief": () => {
        debriefs += 1;
        return json({
          status: debriefs === 1 ? "pending" : "failed",
          outcome: null,
          reached: [],
          debrief: null,
          scores: null,
          flags: [],
          dials: {},
        });
      },
    });
    at();
    await act(async () => {});
    fireEvent.click(screen.getByRole("tab", { name: "Debrief" }));
    expect(screen.queryByText("rapport")).toBeNull(); // the evaluator was still running: no scores yet
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000);
    });
    expect(debriefs).toBe(2); // one reload while pending, then polling stops on failed
    expect(progresses).toBe(2); // the failed debrief still refreshes progress once
    expect(screen.getByText("rapport")).toBeInTheDocument(); // the late scores appear
  });

  it("does not overlap an action refresh with a slow scheduled poll", async () => {
    let calls = 0;
    let active = 0;
    let maximum = 0;
    stubApi({
      "GET sessions/s1/progress": () => {
        calls += 1;
        if (calls === 1) return json(PROGRESS);
        active += 1;
        maximum = Math.max(maximum, active);
        return new Promise<Response>((resolve) =>
          setTimeout(() => {
            active -= 1;
            resolve(json(PROGRESS));
          }, 3000),
        );
      },
      "POST sessions/s1/inject": PROGRESS,
    });
    at();
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000); // this poll's request takes 3 s
    });
    fireEvent.click(screen.getByRole("button", { name: "Shots are heard" }));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    expect(maximum).toBe(1); // the action's refresh waits its turn instead of overlapping the poll
  });
});

describe("Watch: trainer features", () => {
  it("shows CCHN Inject Library and allows injecting FH scenarios directly", async () => {
    let twistText = "";
    stubApi({
      "GET sessions/s1/progress": PROGRESS,
      "POST sessions/s1/twists": (init?: RequestInit) => {
        twistText = (JSON.parse(String(init?.body)) as { text: string }).text;
        return json(progress({ state: { ...PROGRESS.state, injections: [{ id: "inj-1", label: "Politicize", source: "trainer" }] } }));
      },
    });
    at();

    expect(await screen.findByText("CCHN Inject Library (FH)")).toBeInTheDocument();
    expect(screen.getByText("Politicize")).toBeInTheDocument();
    expect(screen.getByText("HQ press release")).toBeInTheDocument();
    expect(screen.getByText("Other agencies accepted")).toBeInTheDocument();

    // Click Inject button for Politicize
    const injectButtons = screen.getAllByRole("button", { name: "Inject" });
    fireEvent.click(injectButtons[0]);
    await act(async () => {});

    expect(twistText).toContain("Who are you really working for?");
  });

  it("switches to Session Plan tab and displays learning objectives and 4-phase protocol", async () => {
    stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();

    const planTab = await screen.findByRole("tab", { name: "Session Plan" });
    fireEvent.click(planTab);

    expect(screen.getByText("PARTICIPANTS ARE ABLE TO:")).toBeInTheDocument();
    expect(screen.getByText("Establish & Maintain Dialogue:")).toBeInTheDocument();
    expect(screen.getByText("4-Phase Exercise Protocol")).toBeInTheDocument();
    expect(screen.getByText("Debrief Reflection Questions (CCHN Grounded)")).toBeInTheDocument();
  });

  it("switches to Observer Sheet tab and displays speaker balance and 6-step checklist", async () => {
    stubApi({ "GET sessions/s1/progress": PROGRESS });
    at();

    const observerTab = await screen.findByRole("tab", { name: "Observer Sheet" });
    fireEvent.click(observerTab);

    expect(screen.getByText("Who is Talking?")).toBeInTheDocument();
    expect(screen.getByText("Who Decides?")).toBeInTheDocument();
    expect(screen.getByText("Who Diverts?")).toBeInTheDocument();
    expect(screen.getByText("6-Step De-escalation Protocol Checklist")).toBeInTheDocument();
    expect(screen.getByText("1. Pause & acknowledge emotion")).toBeInTheDocument();
  });
});

