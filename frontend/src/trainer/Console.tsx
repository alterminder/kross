/** The live console: dial sliders (commit on release), preset twists, a free-text twist, the last turn's rules
 * and goal progress. Shared by the trainer's Watch page and the playtester's panel. */
import { useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import { Problem } from "../ui";
import { GoalPanel } from "./GoalPanel";
import { RulesFired } from "./RulesFired";
import { lastChange, type Injection, type Progress, type TrainerView } from "./progress";

function Dial({
  name,
  value,
  disabled,
  last,
  commit,
}: {
  name: string;
  value: number;
  disabled: boolean;
  last: { delta: number; why: string } | null;
  commit: (value: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState<number | null>(null); // while dragging, then until the commit settles
  const touched = useRef(0); // bumped by every drag and release: an older release must not end a newer draft
  async function release(next: number) {
    touched.current += 1;
    const mine = touched.current;
    if (next === value) {
      setDraft(null); // a no-op release ends its own drag; there is nothing to send
      return;
    }
    setDraft(next);
    try {
      await commit(next); // the draft (the POSTed value) shows until the commit settles
    } catch {
      // a refusal: fall back to the server's value
    }
    if (touched.current === mine) setDraft(null); // the draft ends with the commit; later polls show newer values
  }
  return (
    <label className="dial">
      <span>
        {name.replaceAll("_", " ")} <b>{draft ?? value}</b>
      </span>
      {last && (
        <small className="dial-last">
          {last.delta > 0 ? "▲" : "▼"} {last.delta > 0 ? `+${last.delta}` : `−${Math.abs(last.delta)}`} · {last.why}
        </small>
      )}
      <input
        type="range"
        min="0"
        max="100"
        value={draft ?? value}
        disabled={disabled}
        onChange={(event) => {
          touched.current += 1;
          setDraft(Number(event.target.value));
        }}
        onPointerUp={(event) => void release(Number((event.target as HTMLInputElement).value))}
        onKeyUp={(event) => void release(Number((event.target as HTMLInputElement).value))}
      />
    </label>
  );
}

export const CCHN_INJECTS = [
  {
    id: "fh-politicize",
    label: "Politicize",
    description: "Who are you? Why are you here?",
    text: "Who are you really working for? Why are you here in this region now?",
  },
  {
    id: "fh-hq-release",
    label: "HQ press release",
    description: "External press friction",
    text: "Headquarters just issued a press statement mentioning border tensions that anger local commanders.",
  },
  {
    id: "fh-other-agencies",
    label: "Other agencies accepted",
    description: "Peer compliance pressure",
    text: "Other international NGOs already agreed to our inspection terms without complaining.",
  },
  {
    id: "fh-degradation",
    label: "Degradation signal",
    description: "Impatience & dismissal cue",
    text: "The commander looks at his watch, takes an urgent phone call, and gestures that time is almost up.",
  },
  {
    id: "fh-security-fee",
    label: "Security fee request",
    description: "Financial demand (red line)",
    text: "We require an administrative security contribution before any convoy escort can be scheduled.",
  },
  {
    id: "fh-low-authority",
    label: "Low-authority go-ahead",
    description: "Informal precarious consent",
    text: "I can sign off on this informally right now, but my senior commander might overrule it later.",
  },
];

export function Console({
  view,
  sessionId,
  onChange,
}: {
  view: TrainerView;
  sessionId: string;
  onChange: () => Promise<unknown>;
}) {
  const [twist, setTwist] = useState("");
  const [problem, setProblem] = useState<string>();
  const [applied, setApplied] = useState<Injection | null>(null); // the free-text twist last sent
  const { state } = view;
  const ended = view.status !== "active";
  const fired = new Set(state.injections.map((item) => item.id));
  const noTwists = !view.injectsAllowed; // the current stage forbids them
  const timeIsUp = view.onTimeout === "trainer" && view.secondsLeft === 0 && !ended;
  const [dismissed, setDismissed] = useState(false); // "not yet": hides the time-up card until the next reload

  async function act(work: () => Promise<unknown>) {
    setProblem(undefined);
    try {
      await work();
      await onChange();
    } catch (failure) {
      setProblem(
        failure instanceof ApiError && failure.status === 409
          ? "A turn is running; try again in a moment"
          : (failure as Error).message,
      );
      throw failure; // Dial restores its slider on failure
    }
  }

  async function sendTwist() {
    const text = twist.trim();
    if (!text) return;
    await act(async () => {
      const fresh = await api<Progress>(`sessions/${sessionId}/twists`, { method: "POST", body: { text } });
      const records = (fresh.state.injections ?? []) as Injection[];
      setApplied(records.at(-1) ?? null);
      setTwist("");
    }).catch(() => {}); // the message is already on screen
  }

  async function sendInjectText(text: string) {
    if (!text.trim()) return;
    await act(async () => {
      const fresh = await api<Progress>(`sessions/${sessionId}/twists`, { method: "POST", body: { text } });
      const records = (fresh.state.injections ?? []) as Injection[];
      setApplied(records.at(-1) ?? null);
    }).catch(() => {});
  }

  async function decide(result: "ended" | "fail") {
    await act(() => api(`sessions/${sessionId}/time-decision`, { method: "POST", body: { result } })).catch(() => {});
  }

  return (
    <aside className="console">
      {timeIsUp && !dismissed && (
        <section className="card time-decision" role="alertdialog" aria-label="Time is up">
          <div className="eyebrow">Time is up</div>
          <h2>How does this meeting end?</h2>
          <p>The scenario leaves the end to you. The trainee has been told that the trainer decides.</p>
          <div className="button-grid">
            <button type="button" className="small" onClick={() => void decide("ended")}>
              End the meeting
            </button>
            <button type="button" className="small" onClick={() => void decide("fail")}>
              End as a failure
            </button>
            <button type="button" className="small secondary" onClick={() => setDismissed(true)}>
              Not yet
            </button>
          </div>
        </section>
      )}
      <section className="card">
        <div className="eyebrow">Live console</div>
        <h2>State & controls</h2>
        <Problem text={problem} />
        <div className="dials">
          {Object.entries(state.dials).map(([name, value]) => (
            <Dial
              key={name}
              name={name}
              value={value}
              disabled={ended}
              last={lastChange(state.log, name)}
              commit={(next) => act(() => api(`sessions/${sessionId}/dials`, { method: "POST", body: { dial: name, value: next } }))}
            />
          ))}
        </div>
        {view.presets.length > 0 && (
          <>
            <div className="eyebrow space-top">Preset injections</div>
            <div className="button-grid">
              {view.presets.map((item) => (
                <button
                  type="button"
                  className="small"
                  key={item.id}
                  disabled={fired.has(item.id) || ended || noTwists}
                  onClick={() => void act(() => api(`sessions/${sessionId}/inject`, { method: "POST", body: { injection_id: item.id } })).catch(() => {})}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </>
        )}
        <div className="eyebrow space-top">CCHN Inject Library (FH)</div>
        <div className="cchn-injects-grid">
          {CCHN_INJECTS.map((item) => (
            <div key={item.id} className="cchn-inject-chip">
              <div className="inject-meta">
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </div>
              <div className="inject-actions">
                <button
                  type="button"
                  className="small secondary"
                  title="Insert into text twist"
                  disabled={ended || noTwists}
                  onClick={() => setTwist(item.text)}
                >
                  Insert
                </button>
                <button
                  type="button"
                  className="small"
                  title="Trigger inject directly"
                  disabled={ended || noTwists}
                  onClick={() => void sendInjectText(item.text)}
                >
                  Inject
                </button>
              </div>
            </div>
          ))}
        </div>
        {noTwists && !ended && (
          <p className="hint space-top">
            The {view.stage ?? "current"} stage does not allow twists. They are open again when it ends.
          </p>
        )}
        <label className="field space-top">
          <span>Free-text twist</span>
          <textarea
            rows={3}
            value={twist}
            maxLength={1000}
            placeholder="A new threat appears…"
            onChange={(event) => setTwist(event.target.value)}
          />
        </label>
        <button type="button" disabled={!twist.trim() || ended || noTwists} onClick={() => void sendTwist()}>
          Send twist
        </button>
        {applied && (
          <div className="injection">
            <b>{applied.label}</b> <small>{applied.source}</small>
            {applied.original && <p>Trainer: {applied.original}</p>}
            {applied.rewritten && <p>Director: {applied.rewritten}</p>}
            {applied.bias?.flagged && <p className="flag">Bias check: {applied.bias.reason}</p>}
          </div>
        )}
      </section>
      <section className="card">
        <div className="eyebrow">Last turn</div>
        <h2>Rules fired · turn {state.turn}</h2>
        <RulesFired state={state} turn={state.turn} />
        <p className="hint">Scores, evaluator notes, earlier turns and comments are in the Debrief tab.</p>
      </section>
      <GoalPanel view={view} />
    </aside>
  );
}
