import { useState, type FormEvent } from "react";
import type { S } from "../../api/client";
import { sendCoachQuestion } from "../../api/sse";
import { useLoad } from "../../hooks";
import { Problem } from "../../ui";
import { IconBook, IconGraduationCap, IconMessageSquare } from "../../icons";
import { KnowledgeModal } from "./KnowledgeModal";

interface DebriefCoachProps {
  sessionId: string;
}

interface CoachChatMessage {
  role: "user" | "coach";
  content: string;
  citations?: S["CoachCitationOut"][];
}

export function DebriefCoach({ sessionId }: DebriefCoachProps) {
  const { data: suggestionsData } = useLoad<S["CoachSuggestionsOut"]>(
    `sessions/${sessionId}/coach/suggestions`,
  );
  const [messages, setMessages] = useState<CoachChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string>();
  const [inspectDocId, setInspectDocId] = useState<string | null>(null);

  const ask = async (textToAsk: string) => {
    const q = textToAsk.trim();
    if (!q || busy) return;

    setProblem(undefined);
    setQuestion("");
    setBusy(true);

    const historyPayload = messages.map((m) => ({
      role: m.role === "coach" ? "assistant" : "user",
      content: m.content,
    }));

    const newMessages: CoachChatMessage[] = [
      ...messages,
      { role: "user", content: q },
      { role: "coach", content: "", citations: [] },
    ];
    setMessages(newMessages);

    try {
      for await (const { event: kind, data } of sendCoachQuestion(sessionId, q, historyPayload)) {
        if (kind === "citations") {
          const items = (data.items || data) as S["CoachCitationOut"][];
          setMessages((current) => {
            const last = current[current.length - 1];
            if (last && last.role === "coach") {
              return [...current.slice(0, -1), { ...last, citations: items }];
            }
            return current;
          });
        } else if (kind === "reply") {
          setMessages((current) => {
            const last = current[current.length - 1];
            if (last && last.role === "coach") {
              return [...current.slice(0, -1), { ...last, content: last.content + data.text }];
            }
            return current;
          });
        } else if (kind === "error") {
          setProblem(data.detail);
        }
      }
    } catch (err) {
      setProblem((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(question);
  };

  return (
    <section className="debrief-coach-section" aria-label="Interactive Debrief Coach">
      <div className="coach-header">
        <div className="coach-badge-row">
          <span className="coach-avatar"><IconGraduationCap size={20} /></span>
          <div>
            <h3>Ask the Coach</h3>
            <p className="coach-subtitle">
              Interactive debrief grounded in CCHN Frontline Negotiation Doctrine
            </p>
          </div>
        </div>
      </div>

      {/* Suggested Quick Inquiry Chips */}
      {suggestionsData && suggestionsData.suggestions.length > 0 && messages.length === 0 && (
        <div className="coach-suggestions-wrapper">
          <span className="suggestions-label">Recommended questions for this session:</span>
          <div className="coach-chips">
            {suggestionsData.suggestions.map((sug, idx) => (
              <button
                key={idx}
                type="button"
                className="coach-chip"
                onClick={() => void ask(sug)}
                disabled={busy}
              >
                <IconMessageSquare size={14} /> {sug}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat Thread */}
      {messages.length > 0 && (
        <div className="coach-thread">
          {messages.map((msg, index) => (
            <div key={index} className={`coach-bubble-row ${msg.role}`}>
              <div className="coach-bubble">
                <span className="bubble-speaker">
                  {msg.role === "coach" ? "CCHN Negotiation Coach" : "You"}
                </span>

                {/* Citations if available */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="coach-citations-list">
                    <span className="citations-header">Doctrinal references:</span>
                    <div className="citation-badges">
                      {msg.citations.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className="cchn-citation-badge"
                          onClick={() => setInspectDocId(c.id)}
                          title={`Click to read: ${c.summary}`}
                        >
                          <IconBook size={14} /> {c.title}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="bubble-content">
                  {msg.content || (busy && index === messages.length - 1 ? "Analyzing doctrine and session transcript…" : "")}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Composer */}
      <form onSubmit={handleSubmit} className="coach-composer">
        <input
          type="text"
          placeholder="Ask about counterpart motives, rapport, opening phrases, or CCHN tools…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
          maxLength={800}
        />
        <button type="submit" disabled={busy || !question.trim()} className="btn-coach-send">
          {busy ? "Thinking…" : "Ask Coach"}
        </button>
      </form>

      <Problem text={problem} />

      {/* Doctrine Knowledge Viewer Modal */}
      {inspectDocId && (
        <KnowledgeModal docId={inspectDocId} onClose={() => setInspectDocId(null)} />
      )}
    </section>
  );
}
