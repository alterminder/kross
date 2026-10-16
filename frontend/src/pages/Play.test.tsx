import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { MeContext } from "../me";
import { ME, events, json, renderAt, stubApi } from "../test-utils";
import { Play } from "./Play";

const SESSION = {
  id: "s1",
  scenario_id: "c1",
  title: "Hostile checkpoint",
  cover: "checkpoint",
  mode: "solo",
  status: "active",
  turn: 0,
  brief: { situation: "A roadblock at dawn." },
  transcript: [{ role: "character", text: "Stop there.", turn: 0 }],
  outcome: null,
  debrief_status: null,
};

async function sendText(value: string) {
  const input = await screen.findByLabelText("Your message");
  fireEvent.change(input, { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "End session" })).toBeEnabled());
  return input;
}

/** Drains the send chain's promise steps (no timers involved). */
async function settle() {
  await act(async () => {
    for (let i = 0; i < 30; i++) await Promise.resolve();
  });
}

/** Sends a message without waiting on real timers (for the fake-timer tests). */
async function type(value: string) {
  fireEvent.change(screen.getByLabelText("Your message"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await settle();
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** A body that delivers one chunk, then fails on the next read (error() in start would discard the queued chunk). */
function chunkThenError(chunk: string, message: string) {
  let reads = 0;
  return new ReadableStream({
    pull(controller) {
      if (reads++ === 0) controller.enqueue(new TextEncoder().encode(chunk));
      else controller.error(new TypeError(message));
    },
  });
}

describe("Play", () => {
  it("streams the counterpart's reply into the transcript, incrementally, before the save is read back", async () => {
    let saved = false;
    let finishStream!: () => void;
    let releaseSaved!: () => void;
    const savedGate = new Promise<void>((resolve) => {
      releaseSaved = resolve;
    });
    const encoder = new TextEncoder();
    stubApi({
      "GET sessions/s1": async () => {
        if (!saved) return json(SESSION);
        await savedGate; // the saved transcript arrives only after the partial reply is on screen
        return json({
          ...SESSION,
          turn: 1,
          transcript: [
            ...SESSION.transcript,
            { role: "trainee", text: "Good morning.", turn: 1 },
            { role: "character", text: "I hear you. Go on.", turn: 1 },
          ],
        });
      },
      "POST sessions/s1/turns": () => {
        saved = true;
        return new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode('event: reply\ndata: {"text": "I hear you. "}\n\n'));
              finishStream = () => {
                controller.enqueue(
                  encoder.encode('event: reply\ndata: {"text": "Go on."}\n\nevent: done\ndata: {"turn": 1, "ended": false, "outcome": null}\n\n'),
                );
                controller.close();
              };
            },
          }),
        );
      },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await userEvent.type(await screen.findByLabelText("Your message"), "Good morning.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    // the partial reply renders while the stream is still open and the saved transcript is still pending
    expect(await screen.findByText("I hear you.")).toBeInTheDocument();
    finishStream();
    releaseSaved();
    expect(await screen.findByText("I hear you. Go on.")).toBeInTheDocument();
    expect(screen.getByText("Good morning.")).toBeInTheDocument();
    expect(screen.getByLabelText("Your message")).toHaveValue("");
  });

  it("says the counterpart is thinking until the first reply chunk arrives", async () => {
    let firstChunk!: () => void;
    const encoder = new TextEncoder();
    stubApi({
      "GET sessions/s1": () => json(SESSION),
      "POST sessions/s1/turns": () =>
        new Response(
          new ReadableStream({
            start(controller) {
              firstChunk = () => controller.enqueue(encoder.encode('event: reply\ndata: {"text": "Go on."}\n\n'));
            },
          }),
        ),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    expect(await screen.findByLabelText("Your message")).toBeInTheDocument();
    expect(screen.queryByText("Thinking")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your message"), "Good morning.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Thinking")).toBeInTheDocument();
    firstChunk();
    expect(await screen.findByText("Go on.")).toBeInTheDocument();
    expect(screen.queryByText("Thinking")).not.toBeInTheDocument();
  });

  it("restores the message when the stream ends mid-turn with nothing saved", async () => {
    stubApi({
      "GET sessions/s1": SESSION, // the interrupted turn never committed
      "POST sessions/s1/turns": () => events(["reply", { text: "Partial" }]), // EOF without done or error
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await userEvent.type(await screen.findByLabelText("Your message"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The connection dropped before the turn finished");
    expect(screen.getByLabelText("Your message")).toHaveValue("Hello");
  });

  it("leaves the composer empty when a clean EOF follows a committed turn, and posts once", async () => {
    let saved = false;
    const fetchMock = stubApi({
      "GET sessions/s1": () =>
        json(saved ? { ...SESSION, turn: 1, transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }] } : SESSION),
      "POST sessions/s1/turns": () => {
        saved = true; // the turn committed, but the stream ended before the done event
        return events(["reply", { text: "Reply" }]);
      },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    const input = await screen.findByLabelText("Your message");
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(input).toBeEnabled());
    expect(input).toHaveValue("");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("does not offer to resend a turn that committed before the connection dropped", async () => {
    let saved = false;
    const fetchMock = stubApi({
      "GET sessions/s1": () =>
        json(saved ? { ...SESSION, turn: 1, transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }] } : SESSION),
      "POST sessions/s1/turns": () => {
        saved = true;
        return new Response(new ReadableStream({ start: (controller) => controller.error(new TypeError("connection reset after commit")) }));
      },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    const input = await screen.findByLabelText("Your message");
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(input).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Send" })); // a committed turn must not be sendable again
    await act(async () => {});
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(input).toHaveValue("");
  });

  it("restores a repeated message whose second attempt was not saved", async () => {
    stubApi({
      "GET sessions/s1": { ...SESSION, turn: 1, transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }] }, // turn 1 already says "Hello"
      "POST sessions/s1/turns": () => events(["reply", { text: "Partial" }]), // the second "Hello" ends at EOF, unsaved
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    const input = await screen.findByLabelText("Your message");
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(input).toBeEnabled());
    expect(input).toHaveValue("Hello"); // the earlier turn's "Hello" must not pass for this one
    expect(screen.getByRole("alert")).toHaveTextContent("Nothing was saved");
  });

  it("releases the composer when the reconciliation request fails, and warns that the outcome is unknown", async () => {
    let gets = 0;
    stubApi({
      "GET sessions/s1": () => (++gets === 1 ? json(SESSION) : json({ detail: "temporary" }, 503)),
      "POST sessions/s1/turns": () => events(["reply", { text: "Partial" }]), // EOF without done or error
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    const input = await screen.findByLabelText("Your message");
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(gets).toBeGreaterThan(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "End session" })).toBeEnabled());
    expect(input).toHaveValue("Hello");
    expect(screen.getByRole("alert")).toHaveTextContent("we could not check whether your message was saved");
  });

  it("restores the message when an error follows a partial reply", async () => {
    stubApi({
      "GET sessions/s1": SESSION,
      "POST sessions/s1/turns": () => events(["reply", { text: "Partial" }], ["error", { detail: "The model stopped mid-sentence." }]),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await userEvent.type(await screen.findByLabelText("Your message"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("mid-sentence");
    expect(screen.getByLabelText("Your message")).toHaveValue("Hello");
  });

  it("puts the message back when the turn fails", async () => {
    stubApi({
      "GET sessions/s1": SESSION,
      "POST sessions/s1/turns": () => events(["error", { detail: "The language model did not answer. Send your message again." }]),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await userEvent.type(await screen.findByLabelText("Your message"), "Good morning.");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("did not answer");
    expect(screen.getByLabelText("Your message")).toHaveValue("Good morning.");
  });

  it("shows the limit message when a turn is refused", async () => {
    stubApi({
      "GET sessions/s1": SESSION,
      "POST sessions/s1/turns": () => json({ detail: "You have reached today's practice limit. It resets at 00:00 UTC." }, 429),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await userEvent.type(await screen.findByLabelText("Your message"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("practice limit");
  });

  it("sends on plain Enter only: composing Enter and Shift+Enter stay in the textarea", async () => {
    const fetchMock = stubApi({
      "GET sessions/s1": SESSION,
      "POST sessions/s1/turns": () => events(["done", { turn: 1, ended: false, outcome: null }]),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    const input = await screen.findByLabelText("Your message");
    const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").length;

    fireEvent.change(input, { target: { value: "日本" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true, keyCode: 229 }); // accepts an IME candidate
    expect(posts()).toBe(0);

    fireEvent.keyDown(input, { key: "Enter", shiftKey: true }); // a newline
    expect(posts()).toBe(0);

    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => expect(posts()).toBe(1));
  });

  it("never asks for hidden state in a solo session", async () => {
    const fetchMock = stubApi({ "GET sessions/s1": SESSION });
    renderAt("/play/s1", <Play />, "/play/:id");
    await screen.findByText("Stop there.");
    expect(screen.queryByText("Dials")).toBeNull();
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes("/progress"))).toBe(false);
  });

  it("names speakers by the first role part, including the opening line without a speaker", async () => {
    stubApi({
      "GET sessions/s1": {
        ...SESSION,
        counterparts: [{ id: "cp1", role: "Captain, coastal militia commander, checkpoint boss" }],
        transcript: [
          { role: "character", text: "Stop there.", turn: 0 },
          { role: "character", text: "Papers.", turn: 1, speaker: "cp1" },
        ],
      },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await screen.findByText("Stop there.");
    expect(screen.getAllByText("Captain")).toHaveLength(2); // opening line and speaker line
    expect(screen.queryByText(/coastal militia/)).toBeNull(); // the full role stays out of the dialogue
  });

  it("keeps a speakerless opening on the first counterpart after a channel switch; a silence reply names the selected one", async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve)); // keeps the nudge stream open after its reply
    const fetchMock = stubApi({
      "GET sessions/s1": {
        ...SESSION,
        silence_seconds: 1, // the silence bar shows at once
        counterparts: [
          { id: "cp1", role: "Captain, coastal militia commander" },
          { id: "cp2", role: "Quartermaster, supply officer" },
        ],
        transcript: [
          { role: "character", text: "Stop there.", turn: 0 }, // saved before speakers were recorded
          { role: "character", text: "Manifest.", turn: 1, speaker: "cp2" },
        ],
      },
      "POST sessions/s1/interlocutor": () => new Response(null, { status: 204 }),
      "POST sessions/s1/nudge": () =>
        new Response(
          new ReadableStream({
            async start(controller) {
              controller.enqueue(new TextEncoder().encode('event: reply\ndata: {"text":"Anyone there?"}\n\n'));
              await held;
              controller.enqueue(new TextEncoder().encode('event: done\ndata: {"turn":2,"ended":false,"outcome":null}\n\n'));
              controller.close();
            },
          }),
        ),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await screen.findByText("Stop there.");
    const who = (text: string) => screen.getByText(text).closest("li")!.querySelector(".who")!.textContent;
    expect(who("Stop there.")).toBe("Captain");
    expect(who("Manifest.")).toBe("Quartermaster");
    fireEvent.click(screen.getByRole("button", { name: "Quartermaster" })); // switch to the second channel
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => String(url).includes("interlocutor") && init?.method === "POST")).toBe(true),
    );
    expect(who("Stop there.")).toBe("Captain"); // the old opening stays the first counterpart's
    fireEvent.click(screen.getByRole("button", { name: "Remain silent" }));
    await vi.waitFor(() => expect(who("Anyone there?")).toBe("Quartermaster")); // the live reply names the selected channel
    release();
    await settle();
  });

  it("shows the playtester the steering console and the pinned version's twists, without asking for the scenario", async () => {
    const fetchMock = stubApi({
      "GET sessions/s1": { ...SESSION, mode: "playtest" },
      "GET sessions/s1/progress": {
        session_id: "s1",
        player: "Alice",
        status: "active",
        title: "Hostile checkpoint",
        counterpart: "Checkpoint commander",
        turn_running: false,
        state: { turn: 0, dials: { trust: 2 }, outcome: null, offered: null, reached: [], moves: [], injections: [], flags: [] },
        turns: [],
        injections: [{ id: "shots_heard", label: "Shots are heard" }],
        outcomes: [],
        comments: [],
      },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    expect(await screen.findByRole("slider", { name: /trust/ })).toHaveValue("2");
    expect(await screen.findByRole("button", { name: "Shots are heard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open trainer view" })).toHaveAttribute("href", "/sessions/s1/watch");
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes("/scenarios/"))).toBe(false);
  });

  it("a failed reload after a committed turn must not make the next unsaved turn pass as committed", async () => {
    // Note: this test types into the composer that the same commit locks after a failed reload, via fireEvent
    // (which ignores disabled). No user can reach this state any more; the `known` ref it pins is defense in depth.
    // turn 1 commits with done, but the reload after it fails: the page must not fall back to turn 0 as its baseline
    let gets = 0;
    const turn1 = { ...SESSION, turn: 1, transcript: [...SESSION.transcript, { role: "trainee", text: "First", turn: 1 }] };
    let postsSeen = 0;
    stubApi({
      "GET sessions/s1": () => {
        gets += 1;
        if (gets === 1) return json(SESSION);
        if (gets === 2) return json({ detail: "temporary" }, 503); // the reload after the committed turn 1
        return json(turn1); // reconciliation of turn 2: the server still has only turn 1
      },
      "POST sessions/s1/turns": () =>
        ++postsSeen === 1
          ? events(["reply", { text: "Reply one" }], ["done", { turn: 1, ended: false, outcome: null }])
          : events(["reply", { text: "Partial" }]), // turn 2 ends at EOF without done: not saved
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await sendText("First");
    const input = await sendText("Second");
    expect(input).toHaveValue("Second"); // the unsaved second turn must come back
    expect(screen.getByRole("alert")).toHaveTextContent("Nothing was saved");
  });

  it("after a committed turn whose reload failed, the committed turn stays visible and the composer is closed", async () => {
    let gets = 0;
    stubApi({
      "GET sessions/s1": () => (++gets === 1 ? json(SESSION) : json({ detail: "temporary" }, 503)),
      "POST sessions/s1/turns": () => events(["reply", { text: "Reply one" }], ["done", { turn: 1, ended: false, outcome: null }]),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await sendText("First");
    expect(screen.getByText("First")).toBeInTheDocument(); // the committed message must not vanish
    expect(screen.getByRole("alert")).toHaveTextContent("Your message was saved. Reload the page to continue.");
    expect(screen.getByLabelText("Your message")).toBeDisabled();
  });

  it("an ended session never waits on the debrief finisher's claim", async () => {
    const ended = {
      ...SESSION,
      turn: 1,
      status: "ended",
      turn_running: true, // even a payload still claiming a run must not hold the page: the outcome is known
      outcome: { result: "fail", label: "Red line" },
      transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }],
    };
    let n = 0;
    stubApi({
      "GET sessions/s1": () => (++n === 1 ? json(SESSION) : json(ended)),
      "POST sessions/s1/turns": () => events(["reply", { text: "Part" }]), // EOF before done: the ending turn committed
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await settle();
    fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await settle();
    // turn 1 and status ended are known from the first GET: no wait, no uncertainty, and the outcome is shown
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText(/Session ended/)).toBeInTheDocument();
  });

  it("a transport failure while the server may still be running waits for the turn and never claims that nothing was saved", async () => {
    vi.useFakeTimers();
    try {
      let gets = 0;
      stubApi({
        "GET sessions/s1": () => {
          gets += 1;
          if (gets === 1) return json(SESSION);
          if (gets < 4) return json({ ...SESSION, turn_running: true }); // the server is still running the turn
          return json({
            ...SESSION,
            turn: 1,
            turn_running: false,
            transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }],
          });
        },
        "POST sessions/s1/turns": () => new Response(chunkThenError('event: reply\ndata: {"text": "Part"}\n\n', "network changed")),
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await settle();
      fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "Hello" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await settle();
      expect(screen.getByRole("alert")).toHaveTextContent("Checking whether your message was saved");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4500); // two polls: still running, then committed
      });
      expect(screen.getByLabelText("Your message")).toHaveValue(""); // committed: the composer stays empty
      expect(screen.queryByRole("alert")).toBeNull(); // no "Nothing was saved", and the "Checking…" note is gone
    } finally {
      vi.useRealTimers();
    }
  });

  it("a running turn that never commits gives the text back with the dropped message", async () => {
    vi.useFakeTimers();
    try {
      let gets = 0;
      stubApi({
        "GET sessions/s1": () => {
          gets += 1;
          if (gets === 1) return json(SESSION);
          if (gets < 3) return json({ ...SESSION, turn_running: true });
          return json({ ...SESSION, turn_running: false }); // still turn 0: nothing was saved
        },
        "POST sessions/s1/turns": () => new Response(chunkThenError('event: reply\ndata: {"text": "Part"}\n\n', "network changed")),
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await settle();
      fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "Hello" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500); // one poll: the turn stopped without committing
      });
      expect(screen.getByLabelText("Your message")).toHaveValue("Hello"); // the draft comes back
      expect(screen.getByRole("alert")).toHaveTextContent("The connection dropped before the turn finished. Nothing was saved");
    } finally {
      vi.useRealTimers();
    }
  });

  it("reconciliation says committed, then the reload fails: the turn stays on screen and the composer is closed", async () => {
    const turnOne = { ...SESSION, turn: 1, transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }] };
    let n = 0;
    stubApi({
      "GET sessions/s1": () => {
        n += 1;
        if (n === 1) return json(SESSION);
        if (n === 2) return json(turnOne); // reconciliation: committed
        return json({ detail: "temporary" }, 503); // the reload in finally fails
      },
      "POST sessions/s1/turns": () => new Response(chunkThenError('event: reply\ndata: {"text": "Part"}\n\n', "network changed")),
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await settle();
    await type("Hello");
    expect(screen.getByText("Hello")).toBeInTheDocument(); // the reconciliation-committed turn must not vanish
    expect(screen.getByRole("alert")).toHaveTextContent("Your message was saved. Reload the page to continue.");
    expect(screen.getByLabelText("Your message")).toBeDisabled();
  });

  it("stops polling on unmount: no GET after the page is gone", async () => {
    vi.useFakeTimers();
    try {
      let n = 0;
      stubApi({
        "GET sessions/s1": () => (++n === 1 ? json(SESSION) : json({ ...SESSION, turn_running: true })),
        "POST sessions/s1/turns": () => new Response(chunkThenError('event: reply\ndata: {"text": "Part"}\n\n', "network changed")),
      });
      const view = renderAt("/play/s1", <Play />, "/play/:id");
      await settle();
      await type("Hello");
      await advance(5000);
      const before = n;
      view.unmount();
      await advance(60_000);
      expect(n - before).toBe(0); // not even the already-armed poll fires
    } finally {
      vi.useRealTimers();
    }
  });

  it("the deadline ends the wait with the uncertain message while the turn is still running", async () => {
    vi.useFakeTimers();
    try {
      stubApi({
        "GET sessions/s1": () => json({ ...SESSION, turn_running: true }), // never settles: the claim never clears
        "POST sessions/s1/turns": () => new Response(chunkThenError('event: reply\ndata: {"text": "Part"}\n\n', "network changed")),
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await settle();
      await type("Hello");
      await advance(201_000);
      expect(screen.getByRole("alert")).toHaveTextContent("We could not confirm whether your message was saved");
      expect(screen.getByLabelText("Your message")).toHaveValue("Hello");
    } finally {
      vi.useRealTimers();
    }
  });

  it("one failed poll does not end the wait: a later commit is recognised", async () => {
    vi.useFakeTimers();
    try {
      let n = 0;
      stubApi({
        "GET sessions/s1": () => {
          n += 1;
          if (n === 1) return json(SESSION);
          if (n === 2) return json({ ...SESSION, turn_running: true });
          if (n === 3) throw new TypeError("Failed to fetch"); // one flaky poll
          return json({ ...SESSION, turn: 1, turn_running: false, transcript: [...SESSION.transcript, { role: "trainee", text: "Hello", turn: 1 }] });
        },
        "POST sessions/s1/turns": () => new Response(chunkThenError('event: reply\ndata: {"text": "Part"}\n\n', "network changed")),
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await settle();
      await type("Hello");
      await advance(5000); // the blip, then the commit on the next poll
      expect(screen.getByLabelText("Your message")).toHaveValue("");
      expect(screen.queryByRole("alert")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("the turn baseline resets when the route param changes in place", async () => {
    const s2 = { ...SESSION, id: "s2" };
    let s2gets = 0;
    stubApi({
      "GET sessions/s1": { ...SESSION, turn: 5 },
      "POST sessions/s1/turns": () => events(["done", { turn: 6, ended: false, outcome: null }]),
      "GET sessions/s2": () =>
        ++s2gets === 1 ? json(s2) : json({ ...s2, turn: 1, transcript: [...s2.transcript, { role: "trainee", text: "Hi", turn: 1 }] }),
      "POST sessions/s2/turns": () => events(["reply", { text: "Part" }]), // EOF, but the turn committed
    });
    function Jump() {
      const navigate = useNavigate();
      return <button onClick={() => navigate("/play/s2")}>jump</button>;
    }
    render(
      <MeContext.Provider value={ME}>
        <MemoryRouter initialEntries={["/play/s1"]}>
          <Jump />
          <Routes>
            <Route path="/play/:id" element={<Play />} />
          </Routes>
        </MemoryRouter>
      </MeContext.Provider>,
    );
    await screen.findByLabelText("Your message");
    await type("First");
    fireEvent.click(screen.getByRole("button", { name: "jump" }));
    await screen.findByLabelText("Your message");
    await type("Hi");
    // s2 went 0 -> 1: its committed turn must not be judged against s1's turn count
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByLabelText("Your message")).toHaveValue("");
  });

  it("renders negotiation phase HUD according to current session phase", async () => {
    stubApi({
      "GET sessions/s1": { ...SESSION, turn: 4, phase: "exploration" },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await screen.findByLabelText("Your message");
    const hud = screen.getByRole("region", { name: "Negotiation Phase" });
    expect(hud).toHaveTextContent("Exploration");
    expect(hud).toHaveTextContent("Turn 4");
    expect(hud).toHaveTextContent("Substantive discussion of issues, interests & trade-offs");
  });

  it("shows the scenario's own stages and their hints, and uses its own warning times", async () => {
    stubApi({
      "GET sessions/s1": {
        ...SESSION,
        turn: 2,
        phase: "the_ask",
        phases: [
          { id: "cold_start", label: "Cold start", hint: "He says little." },
          { id: "the_ask", label: "The ask", hint: "He wants terms." },
        ],
        minutes_total: 20,
        seconds_left: 170, // under the scenario's own 3-minute warning, not the default 5
        warning_minutes: [3],
      },
    });
    renderAt("/play/s1", <Play />, "/play/:id");
    await screen.findByLabelText("Your message");
    const hud = screen.getByRole("region", { name: "Negotiation Phase" });
    expect(hud).toHaveTextContent("Cold start");
    expect(hud).toHaveTextContent("The ask");
    expect(hud).not.toHaveTextContent("Opening"); // the built-in stages are replaced, not added to
    expect(hud).toHaveTextContent("He wants terms.");
    expect(screen.getByRole("status")).toHaveTextContent("3 minutes left");
  });

  it("asks the server to end the meeting when the clock runs out, if the scenario's rules say so", async () => {
    vi.useFakeTimers();
    try {
      let session: Record<string, unknown> = { ...SESSION, minutes_total: 10, seconds_left: 3, on_timeout: "end" };
      const timeUp = vi.fn(() => {
        session = { ...session, status: "ended", seconds_left: null, outcome: { result: "ended", label: "Time ran out" } };
        return json(session);
      });
      stubApi({ "GET sessions/s1": () => json(session), "POST sessions/s1/time-up": timeUp });
      renderAt("/play/s1", <Play />, "/play/:id");
      await act(async () => {});
      expect(timeUp).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(timeUp).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/Session ended: Time ran out/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not ask when the scenario only guides", async () => {
    vi.useFakeTimers();
    try {
      const timeUp = vi.fn(() => json({}));
      stubApi({
        "GET sessions/s1": { ...SESSION, minutes_total: 10, seconds_left: 2, on_timeout: "guide" },
        "POST sessions/s1/time-up": timeUp,
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      expect(timeUp).not.toHaveBeenCalled();
      expect(screen.getByRole("status")).toHaveTextContent("Time is up");
    } finally {
      vi.useRealTimers();
    }
  });

  it("waits as long as the scenario says before the counterpart speaks up", async () => {
    vi.useFakeTimers();
    try {
      let nudged = 0;
      stubApi({
        "GET sessions/s1": { ...SESSION, silence_seconds: 20 },
        "POST sessions/s1/nudge": () => {
          nudged += 1;
          return events(["reply", { text: "Was there anything else?" }], ["done", { turn: 1, ended: false, outcome: null }]);
        },
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await act(async () => {});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(9000);
      });
      expect(screen.queryByRole("alert")).toBeNull(); // half of 20 s has not passed
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(screen.getByRole("alert")).toHaveTextContent("Counterpart waiting (9s remaining)");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(nudged).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows silence warning after idle time and allows triggering silence nudge", async () => {
    vi.useFakeTimers();
    try {
      let nudgeCalled = false;
      stubApi({
        "GET sessions/s1": SESSION,
        "POST sessions/s1/nudge": () => {
          nudgeCalled = true;
          return events(
            ["reply", { text: "Delegate, are you still there?" }],
            ["done", { turn: 1, ended: false, outcome: null }],
          );
        },
      });
      renderAt("/play/s1", <Play />, "/play/:id");
      await settle();
      expect(screen.getByLabelText("Your message")).toBeInTheDocument();
      expect(screen.queryByText(/Counterpart waiting/)).toBeNull();

      // Advance by 46 seconds to trigger silence bar
      await advance(46000);
      expect(screen.getByText(/Counterpart waiting/)).toBeInTheDocument();
      const remainSilentBtn = screen.getByRole("button", { name: "Remain silent" });
      fireEvent.click(remainSilentBtn);
      await settle();
      expect(nudgeCalled).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("pauses the idle timer while onboarding is open and does not auto-nudge after 90 seconds", async () => {
    vi.useFakeTimers();
    try {
      let nudgeCalled = false;
      stubApi({
        "GET sessions/s1": SESSION,
        "POST sessions/s1/nudge": () => {
          nudgeCalled = true;
          return events(
            ["reply", { text: "Delegate, are you still there?" }],
            ["done", { turn: 1, ended: false, outcome: null }],
          );
        },
      });
      renderAt("/play/s1?onboard=1", <Play />, "/play/:id");
      await settle();

      expect(screen.getByRole("dialog", { name: "Simulation Onboarding" })).toBeInTheDocument();

      // Advance by 95 seconds while onboarding is open
      await advance(95000);
      expect(nudgeCalled).toBe(false);
      expect(screen.queryByText(/Counterpart waiting/)).toBeNull();

      // Close onboarding modal
      const skipBtn = screen.getByRole("button", { name: "Skip to negotiation" });
      fireEvent.click(skipBtn);
      await settle();

      // Now onboarding is closed. Advance by 46 seconds to trigger warning
      await advance(46000);
      expect(screen.getByText(/Counterpart waiting/)).toBeInTheDocument();

      // Advance remaining time to reach 90s total idle
      await advance(45000);
      await settle();
      expect(nudgeCalled).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
