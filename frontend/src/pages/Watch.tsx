import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router";
import type { S } from "../api/client";
import { useLoad } from "../hooks";
import { Chat } from "../trainer/Chat";
import { Console } from "../trainer/Console";
import { DialChart } from "../trainer/DialChart";
import { ObserverSheet } from "../trainer/ObserverSheet";
import { PromptView } from "../trainer/PromptView";
import { SessionPlan } from "../trainer/SessionPlan";
import { TurnReview } from "../trainer/TurnReview";
import { TERMINAL, useProgress, viewOf, type TrainerView } from "../trainer/progress";
import { Problem, Value } from "../ui";

/** The written debrief (summary, strengths, improvements), once the session has ended. */
function DebriefCard({ debrief }: { debrief: S["DebriefOut"] }) {
  return (
    <section className="card">
      <div className="eyebrow">After action</div>
      <h2>Debrief</h2>
      {debrief.status === "pending" && <p>Writing the debrief… this updates by itself.</p>}
      {debrief.status === "failed" && <p>The debrief could not be written; the scores still apply.</p>}
      {debrief.status === "unavailable" && <p>No language model is configured, so there is no written debrief.</p>}
      {debrief.debrief && <Value value={debrief.debrief} />}
      <p className="hint">The feedback is written by the model. It cannot change the outcome or the dials.</p>
    </section>
  );
}

/** The trainer's view of a session: the Live session tab (chat plus the steering console), the Session Plan, the Observer Sheet, and the Debrief tab. */
export function Watch() {
  const { id } = useParams() as { id: string };
  const { data, error, reload } = useProgress(id);
  const [tab, setTab] = useState<"live" | "plan" | "observer" | "debrief">("live");
  const [replay, setReplay] = useState<number | null>(null); // the turn under review; null follows the latest
  const debrief = useLoad<S["DebriefOut"]>(data?.status === "ended" ? `sessions/${id}/debrief` : null);
  const scored = useRef(false);
  useEffect(() => {
    if (debrief.status !== undefined && TERMINAL.has(debrief.status)) return; // 401/403/404/410: retrying will not fix these
    const waiting = debrief.data === undefined ? debrief.status !== undefined : debrief.data.status === "pending";
    if (!waiting) return; // ready, failed or unavailable: done; a first request still in flight: wait for it
    const timer = setTimeout(() => void debrief.reload(), 3000); // written in the background; poll while pending, retry a transient failure
    return () => clearTimeout(timer);
  }, [debrief.data, debrief.status, debrief.settled, debrief.reload]);
  useEffect(() => {
    const done = debrief.data?.status === "ready" || debrief.data?.status === "failed"; // either way the final scores are committed
    if (done && !scored.current) {
      scored.current = true; // background work finished: refresh progress once, so the late scores appear
      void reload();
    }
  }, [debrief.data, reload]);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  const view: TrainerView = viewOf(data);
  const reviewTurn = replay ?? view.state.turn;
  const outcome = view.state.outcome;
  return (
    <>
      <div className="tabs" role="tablist">
        {(
          [
            { id: "live", label: "Live session" },
            { id: "plan", label: "Session Plan" },
            { id: "observer", label: "Observer Sheet" },
            { id: "debrief", label: "Debrief" },
          ] as const
        ).map((item) => (
          <button
            type="button"
            role="tab"
            key={item.id}
            aria-selected={tab === item.id}
            className={`tab ${tab === item.id ? "active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === "live" && (
        <div className="session-layout">
          <div className="main-column">
            <Chat view={view} />
          </div>
          <Console
            view={view}
            sessionId={id}
            onChange={async () => {
              await reload();
            }}
          />
        </div>
      )}
      {tab === "plan" && <SessionPlan view={view} title={data.title} />}
      {tab === "observer" && <ObserverSheet view={view} sessionId={id} />}
      {tab === "debrief" && (
        <>
          <Problem text={debrief.error} />
          <div className="debrief-grid">
            <div className="debrief-page">
              <section className="card">
                <div className="eyebrow">Session summary</div>
                <h2>Debrief — {data.title}</h2>
                <p>
                  {outcome ? (
                    <>
                      <b>Outcome:</b> {outcome.label} —{" "}
                      <b className={`result ${outcome.result}`}>{outcome.result.toUpperCase()}</b> (turn{" "}
                      {outcome.turn ?? view.state.turn})
                    </>
                  ) : (
                    <>In progress, turn {view.state.turn}. The debrief fills in as the session runs.</>
                  )}
                  {view.state.reached.map((item) => (
                    <span key={item.id}>
                      <br />
                      <b>Milestone:</b> {item.label} (turn {item.turn})
                    </span>
                  ))}
                </p>
              </section>
              <DialChart view={view} turn={reviewTurn} onPick={setReplay} />
              {debrief.data && <DebriefCard debrief={debrief.data} />}
            </div>
            <TurnReview
              view={view}
              sessionId={id}
              turn={reviewTurn}
              setTurn={setReplay}
              following={replay === null}
              onChange={async () => {
                await reload();
              }}
            />
          </div>
          <PromptView view={view} turn={reviewTurn} />
        </>
      )}
    </>
  );
}
