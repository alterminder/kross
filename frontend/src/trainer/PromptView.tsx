/** Exactly what the counterpart model was sent on a turn (the request stored with it), shown when opened. */
import { useState } from "react";
import type { TrainerView } from "./progress";

// The system message is instructions followed by one JSON state object: show that object indented.
function readable(content: string) {
  const at = content.indexOf("{");
  if (at < 0) return content;
  try {
    return `${content.slice(0, at).trim()}\n\n${JSON.stringify(JSON.parse(content.slice(at)), null, 2)}`;
  } catch {
    return content;
  }
}

export function PromptView({ view, turn }: { view: TrainerView; turn: number }) {
  const [open, setOpen] = useState(false);
  const sent = view.requests[turn];
  return (
    <section className="card prompt-view">
      <details open={open}>
        <summary
          onClick={(event) => {
            event.preventDefault(); // controlled: `open` is React state, so tests can toggle it too
            setOpen(!open);
          }}
        >
          <span className="caret" aria-hidden="true" />
          <div>
            <div className="eyebrow">Frozen prompt · turn {turn}</div>
            <h2>What the counterpart model was sent</h2>
          </div>
        </summary>
        {open && !sent && (
          <p className="hint">No counterpart request on turn {turn}. Turns without a reply have none.</p>
        )}
        {open && sent && (
          <div className="prompt-call">
            <p className="hint">
              model {sent.model} · temperature {sent.temperature}
            </p>
            {sent.messages.map((message, j) => (
              <div className={`prompt-message ${message.role}`} key={j}>
                <span className="speaker">
                  {message.role === "system"
                    ? "System: instructions and state"
                    : message.role === "user"
                      ? "User: trainee"
                      : "Assistant: counterpart"}
                </span>
                <pre>{message.role === "system" ? readable(message.content) : message.content}</pre>
              </div>
            ))}
          </div>
        )}
      </details>
    </section>
  );
}
