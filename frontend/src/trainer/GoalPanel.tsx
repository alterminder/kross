/** Goal progress: one line per test in an outcome rule, ✓ met, ✗ unmet, · not judgable from the console.
 * Ported from the POC's goalChecks/GoalPanel. */
import type { TrainerView } from "./progress";

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
type Check = { text: string; ok: boolean | null };
type State = TrainerView["state"];

export function merge(checks: Check[], joiner: string): Check {
  return {
    text: checks.map((check) => check.text).join(joiner),
    ok: checks.some((check) => check.ok === false) ? false : checks.every((check) => check.ok === true) ? true : null,
  };
}

// ok is null when a test cannot be judged from the console (moves and proposals are per turn).
export function goalChecks(when: Json, state: State, agreed: boolean | null): Check[] {
  if (!when || typeof when !== "object" || Array.isArray(when)) return [];
  return Object.entries(when).map(([key, value]): Check => {
    if (key === "any" || key === "all") {
      const parts = (value as Json[]).map((item) => merge(goalChecks(item, state, agreed), " and "));
      const oks = parts.map((part) => part.ok);
      return {
        text: parts.map((part) => part.text).join(key === "any" ? " or " : " and "),
        ok:
          key === "any"
            ? oks.includes(true)
              ? true
              : oks.every((ok) => ok === false)
                ? false
                : null
            : oks.includes(false)
              ? false
              : oks.every((ok) => ok === true)
                ? true
                : null,
      };
    }
    if (key === "goal_requested") return { text: "the counterpart says yes in its own words", ok: agreed }; // asking is not agreeing
    if (key === "level") return { text: `level is ${value}`, ok: state.level === value };
    const range = key.match(/^(.+)_(gte|lte)$/);
    if (range) {
      const now = range[1] === "turn" ? state.turn : state.dials?.[range[1]];
      const up = range[2] === "gte";
      return {
        text: `${range[1]} ${up ? "≥" : "≤"} ${value} (now ${now ?? "?"})`,
        ok: now === undefined ? null : up ? now >= Number(value) : now <= Number(value),
      };
    }
    return { text: `${key.replaceAll("_", " ")} ${typeof value === "object" ? "" : String(value)}`.trim() + " (per turn)", ok: null };
  });
}

export function GoalPanel({ view }: { view: TrainerView }) {
  const { state } = view;
  const rules = view.outcomes;
  return (
    <section className="card">
      <div className="eyebrow">Goal</div>
      <h2>Goal progress</h2>
      {state.outcome ? (
        <p className={`hint result ${state.outcome.result}`}>
          Reached: {state.outcome.label} ({state.outcome.result}, turn {state.outcome.turn ?? state.turn})
        </p>
      ) : state.offered ? (
        <p className="hint">
          The dials allow “{state.offered.label}” since turn {state.offered.turn}, so the counterpart is told to offer
          it and to agree once the trainee accepts.{" "}
          {state.offered.result === "success"
            ? "The session ends when the counterpart says yes."
            : "A milestone: the session continues after it."}
        </p>
      ) : (
        <p className="hint">
          When an outcome's dial ranges are met, the counterpart is told to offer it. Only the goal (success) ends the
          session when the counterpart says yes; a partial outcome is a milestone.
        </p>
      )}
      {state.reached.map((item) => (
        <p className="hint result partial" key={item.id}>
          Milestone: {item.label} (turn {item.turn}). The session continues.
        </p>
      ))}
      {rules.map((rule) => (
        <div className={`goal ${rule.result}`} key={rule.id}>
          <div>
            <b>{rule.label}</b> <small>{rule.result === "partial" ? "partial · milestone" : rule.result}</small>
          </div>
          <ul>
            {goalChecks(
              rule.when as Json,
              state,
              state.outcome?.id === rule.id || state.reached.some((item) => item.id === rule.id) ? true : null,
            ).map((check, i) => (
              <li key={i} className={check.ok === true ? "met" : check.ok === false ? "unmet" : "na"}>
                {check.ok === true ? "✓" : check.ok === false ? "✗" : "·"} {check.text}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
