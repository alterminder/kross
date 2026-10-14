/** The trainer's view of a session: ProgressOut adapted to the POC's shape, and the 2 s polling hook. */
import { useCallback, useEffect, useRef } from "react";
import type { S } from "../api/client";
import { useLoad } from "../hooks";

export type Progress = S["ProgressOut"];

export type Line = { role: "trainee" | "character"; text: string; turn: number };
export type EngineEvent = {
  turn: number;
  source: string;
  kind: string;
  dial?: string | null;
  before?: number | null;
  after?: number | null;
  ref?: string | null;
  quote?: string | null;
  cue?: { kind: string; text: string; label: string } | null;
  reason?: string;
  text?: string;
};
export type Move = { turn: number; id: string; quote: string };
export type Flag = { turn: number; id: string; quote: string; text?: string };
export type Injection = {
  id: string;
  label: string;
  source: string;
  turn: number;
  original?: string | null;
  rewritten?: string | null;
  bias?: { flagged: boolean; reason: string } | null;
};
export type Score = { id: string; score: number | null; quote: string };
export type TurnScores = { turn: number; scores: Score[]; flags: { text: string; quote: string }[]; error?: string };
export type Outcome = { id?: string; label: string; result: string; turn?: number };
export type Offer = { id: string; label: string; result: string; turn: number };
export type Comment = { turn: number; text: string; author: string; created_at: string };
export type FrozenRequest = {
  model: string;
  temperature: number;
  messages: { role: string; content: string }[];
};

/** What the trainer components render: the POC's SessionView, built from ProgressOut. */
export type TrainerView = {
  id: string;
  title: string;
  player: string;
  status: string;
  turnRunning: boolean;
  counterpart: string;
  presets: { id: string; label: string }[]; // the pinned version's preset twists
  stage: string | null; // the meeting's current stage, by its trainee-facing name
  injectsAllowed: boolean; // false: the current stage refuses a twist
  secondsLeft: number | null; // of the scenario's minutes, while active
  onTimeout: string; // what the scenario does when they run out: guide | end | fail | trainer
  outcomes: S["OutcomeOut"][]; // the pinned version's outcome rules
  comments: Comment[];
  dialsByTurn: { turn: number; dials: Record<string, number> }[]; // the dials after each turn, for the chart
  requests: Record<number, FrozenRequest>; // the counterpart's frozen prompt per turn, when recorded
  state: {
    turn: number;
    dials: Record<string, number>;
    level?: string;
    goalRequested?: boolean;
    outcome: Outcome | null;
    offered: Offer | null;
    reached: Outcome[];
    history: Line[];
    log: EngineEvent[];
    moves: Move[];
    flags: Flag[];
    injections: Injection[];
    scores: TurnScores[];
  };
};

export function viewOf(progress: Progress): TrainerView {
  const state = progress.state as {
    turn?: number;
    dials?: Record<string, number>;
    level?: string;
    goal_requested?: boolean;
    outcome?: Outcome | null;
    offered?: Offer | null;
    reached?: Outcome[];
    moves?: Move[];
    injections?: Injection[];
    flags?: Flag[];
  };
  return {
    id: progress.session_id,
    title: progress.title,
    player: progress.player,
    status: progress.status,
    turnRunning: progress.turn_running,
    counterpart: progress.counterpart,
    presets: progress.injections,
    stage: progress.phase_label ?? null,
    injectsAllowed: progress.injects_allowed ?? true,
    secondsLeft: progress.seconds_left ?? null,
    onTimeout: progress.on_timeout ?? "guide",
    outcomes: progress.outcomes,
    comments: progress.comments,
    dialsByTurn: progress.turns.map((turn) => ({ turn: turn.number, dials: turn.dials })),
    requests: Object.fromEntries(
      progress.turns
        .filter((turn) => turn.counterpart_request)
        .map((turn) => [turn.number, turn.counterpart_request as FrozenRequest]),
    ),
    state: {
      turn: state.turn ?? 0,
      dials: state.dials ?? {},
      level: state.level,
      goalRequested: state.goal_requested,
      outcome: state.outcome ?? null,
      offered: state.offered ?? null,
      reached: state.reached ?? [],
      history: progress.turns.flatMap((turn) => [
        ...(turn.trainee_text ? [{ role: "trainee" as const, text: turn.trainee_text, turn: turn.number }] : []),
        ...(turn.reply_text ? [{ role: "character" as const, text: turn.reply_text, turn: turn.number }] : []),
      ]),
      log: progress.turns.flatMap((turn) => (turn.events ?? []) as EngineEvent[]),
      moves: state.moves ?? [],
      flags: state.flags ?? [],
      injections: state.injections ?? [],
      scores: progress.turns
        .filter((turn) => turn.scores !== null)
        .map((turn) => ({ turn: turn.number, ...(turn.scores as Omit<TurnScores, "turn">) })),
    },
  };
}

const TERMINAL = new Set([401, 403, 404, 410]); // signing in again or a gone session: polling will not fix these

export { TERMINAL };

/** GETs the session's progress, then polls every 2 s while it is active. Scheduled polls and explicit refreshes (a
 * trainer action, a completed turn) share one in-flight request: a refresh asked for during a request queues exactly
 * one follow-up fetch after it. */
export function useProgress(sessionId: string) {
  const load = useLoad<Progress>(`sessions/${sessionId}/progress`);
  const { data, status, reload, lastStatus } = load;
  const terminal = status !== undefined && TERMINAL.has(status);
  const active = data?.status === "active" && !terminal; // a deleted session must not be polled forever
  const running = useRef<Promise<void> | null>(null);
  const queued = useRef(false);
  const refresh = useCallback((): Promise<void> => {
    if (running.current) {
      queued.current = true; // one queued follow-up covers any number of callers
      return running.current;
    }
    running.current = (async () => {
      try {
        do {
          queued.current = false;
          await reload();
        } while (queued.current && (lastStatus.current === undefined || !TERMINAL.has(lastStatus.current))); // a terminal response ends the run: no queued follow-up
      } finally {
        running.current = null;
      }
    })();
    return running.current;
  }, [reload]);
  useEffect(() => {
    if (!active) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      await refresh();
      if (!stopped) timer = setTimeout(poll, 2000); // one request at a time: the next poll starts after this one settles
    };
    timer = setTimeout(poll, 2000); // polling; live push is on the roadmap
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [active, refresh]);
  return { ...load, reload: refresh, active };
}

/** The last real change to a dial and what caused it, for the live dial card. null when it never moved. */
export function lastChange(log: EngineEvent[], dial: string): { delta: number; why: string } | null {
  const event = [...log].reverse().find((item) => item.kind === "dial" && item.dial === dial && item.after !== item.before);
  if (!event) return null;
  const delta = (event.after ?? 0) - (event.before ?? 0);
  const ref = (event.ref ?? "").replaceAll("_", " ");
  const why =
    event.source === "move"
      ? event.quote
        ? `${ref} · “${event.quote}”`
        : ref
      : event.source === "trainer" && event.reason === "manual override"
        ? "set by hand"
        : event.reason || (ref ? `twist: ${ref}` : event.source);
  return { delta, why };
}
