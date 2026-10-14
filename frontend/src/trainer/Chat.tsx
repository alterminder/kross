/** The transcript as the POC's chat bubbles, read-only for the trainer: no composer. */
import { useEffect, useRef } from "react";
import type { TrainerView } from "./progress";

export function Chat({ view }: { view: TrainerView }) {
  const { state } = view;
  const end = useRef<HTMLDivElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [state.history.length, view.turnRunning]);
  return (
    <section className="card chat">
      <div className="card-head">
        <div>
          <div className="eyebrow">Trainer view · {view.player} · {view.status}</div>
          <h2>{view.title}</h2>
        </div>
        <div className="chat-head-actions">
          <span className="badge">Turn {state.turn}</span>
        </div>
      </div>
      <div className="messages" aria-live="polite">
        {state.history.map((item, index) => (
          <div key={`${item.turn}-${index}`} className={`message ${item.role}`}>
            <span className="speaker">
              {item.role === "trainee" ? "Trainee" : "Counterpart"} · {item.turn}
            </span>
            <p>{item.text}</p>
          </div>
        ))}
        {view.turnRunning && (
          <div className="message character thinking" role="status">
            <span className="speaker">Counterpart</span>
            <p>
              Counterpart is thinking
              <span className="dots" aria-hidden="true">
                <span>.</span>
                <span>.</span>
                <span>.</span>
              </span>
            </p>
          </div>
        )}
        <div ref={end} />
      </div>
      {state.outcome && (
        <div className={`outcome ${state.outcome.result}`}>
          <strong>{state.outcome.label}</strong>
          <span>{state.outcome.result}</span>
        </div>
      )}
    </section>
  );
}
