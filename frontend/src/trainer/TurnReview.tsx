/** One turn under review: its messages, the rules that fired, the evaluator's scores and notes, trainer
 * interventions and comments. Ported from the POC; comments POST to /comments. */
import { useState } from "react";
import { api } from "../api/client";
import { Problem } from "../ui";
import { RulesFired } from "./RulesFired";
import type { TrainerView } from "./progress";

export function TurnReview({
  view,
  sessionId,
  turn,
  setTurn,
  following,
  onChange,
}: {
  view: TrainerView;
  sessionId: string;
  turn: number;
  setTurn: (turn: number | null) => void;
  following: boolean;
  onChange: () => Promise<unknown>;
}) {
  const [comment, setComment] = useState("");
  const [problem, setProblem] = useState<string>();
  const { state } = view;
  // Scores are written in the background after each turn; show the newest set made up to this turn.
  const scores = [...state.scores].filter((item) => item.turn <= turn).sort((a, b) => b.turn - a.turn)[0];
  const messages = state.history.filter((item) => item.turn === turn);
  const injections = state.injections.filter((item) => item.turn === turn);
  const comments = view.comments.filter((item) => item.turn === turn);

  async function addComment() {
    const text = comment.trim();
    if (!text) return;
    setProblem(undefined);
    try {
      await api(`sessions/${sessionId}/comments`, { method: "POST", body: { turn, text } });
      setComment("");
      await onChange();
    } catch (failure) {
      setProblem((failure as Error).message);
    }
  }

  return (
    <aside className="turn-review">
      <section className="card">
        <div className="card-head">
          <div>
            <div className="eyebrow">Turn review</div>
            <h2>
              Turn {turn} of {state.turn}
            </h2>
          </div>
          <button type="button" className="small ghost" disabled={following} onClick={() => setTurn(null)}>
            Follow latest
          </button>
        </div>
        <input
          className="replay-slider"
          aria-label="Turn to review"
          type="range"
          min="0"
          max={Math.max(0, state.turn)}
          value={turn}
          onChange={(event) => setTurn(Number(event.target.value))}
        />
        <div className="turn-messages">
          {messages.length ? (
            messages.map((item, i) => (
              <div key={i} className={`message ${item.role}`}>
                <span className="speaker">{item.role === "trainee" ? "Trainee" : "Counterpart"}</span>
                <p>{item.text}</p>
              </div>
            ))
          ) : (
            <p className="hint">No messages on this turn.</p>
          )}
        </div>
      </section>
      <section className="card">
        <div className="eyebrow">Rules · decide</div>
        <h2>Rules fired</h2>
        <RulesFired state={state} turn={turn} />
      </section>
      <section className="card">
        <div className="eyebrow">Evaluator · no effect on the outcome</div>
        <h2>Scores & evidence</h2>
        {scores && scores.turn !== turn && <p className="hint">Latest scores made up to this turn (turn {scores.turn}).</p>}
        {scores?.error && <p className="hint">{scores.error}</p>}
        {scores?.scores?.length ? (
          scores.scores.map((item) => (
            <div className="score" key={item.id}>
              <span>{item.id.replaceAll("_", " ")}</span>
              <b>{item.score ?? "—"} / 5</b>
              {item.quote && <blockquote>“{item.quote}”</blockquote>}
            </div>
          ))
        ) : (
          <p className="hint">Scores appear after the first turn.</p>
        )}
        {(scores?.flags || []).length > 0 && (
          <>
            <h3>Evaluator notes</h3>
            {scores!.flags.map((item, i) => (
              <p className="note" key={i}>
                {item.text}: “{item.quote}”
              </p>
            ))}
          </>
        )}
      </section>
      <section className="card">
        <div className="eyebrow">Trainer</div>
        <h2>Interventions & comments</h2>
        {injections.map((item, i) => (
          <div className="injection" key={i}>
            <b>{item.label}</b> <small>{item.source}</small>
            {item.original && <p>Trainer: {item.original}</p>}
            {item.rewritten && <p>Director: {item.rewritten}</p>}
            {item.bias?.flagged && <p className="flag">Bias check: {item.bias.reason}</p>}
          </div>
        ))}
        {comments.map((item, i) => (
          <p key={i} className="comment">
            {item.text}
          </p>
        ))}
        {!injections.length && !comments.length && <p className="hint">Nothing on this turn.</p>}
        <Problem text={problem} />
        <div className="comment-form">
          <input
            aria-label="Add review comment"
            placeholder={`Comment on turn ${turn}`}
            value={comment}
            maxLength={2000}
            onChange={(event) => setComment(event.target.value)}
          />
          <button type="button" className="small" disabled={!comment.trim()} onClick={() => void addComment()}>
            Add
          </button>
        </div>
      </section>
    </aside>
  );
}
