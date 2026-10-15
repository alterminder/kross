import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { ApiError, api, type S } from "../api/client";
import { sendNudge, sendTurn } from "../api/sse";
import { SessionClock } from "../features/play/SessionClock";
import { GlossaryModal } from "../features/play/GlossaryModal";
import { OnboardingCarousel } from "../features/onboarding/OnboardingCarousel";
import { PreparationView } from "../features/preparation/PreparationView";
import { useLoad } from "../hooks";
import { useMe } from "../me";
import { hidePrep } from "../prep";
import { Console } from "../trainer/Console";
import { useProgress, viewOf } from "../trainer/progress";
import { Problem } from "../ui";
import { IconBook, IconClipboard, IconGlobe, IconHourglass, IconMap, IconShield } from "../icons";

/** The stages when the server sends none (an older server). The scenario's own stages come with the session. */
const DEFAULT_PHASES: S["PhaseOut"][] = [
  { id: "opening", label: "Opening", hint: "Formal protocol, assessing mandate & credentials" },
  { id: "exploration", label: "Exploration", hint: "Substantive discussion of issues, interests & trade-offs" },
  { id: "closing", label: "Closing", hint: "Time constraints & pressing for final terms" },
];

type Line = { role: "trainee" | "character" | "notice"; text: string; speaker?: string | null };

/** The short dialogue name: the role's first comma-separated part ("Captain, coastal militia…" → "Captain").
 * The full role stays in the brief and the counterpart titles. */
function shortRole(role?: string | null): string {
  return (role ?? "").split(",")[0].trim();
}

function getSpeakerLabel(line: Line, session?: S["SessionOut"]): string {
  if (line.role === "trainee") return "You";
  if (line.role === "notice") return "";
  // a saved opening without a speaker is the first counterpart's line, whatever channel is selected now
  const speaker = line.speaker || session?.counterparts?.[0]?.id;
  if (speaker && session) {
    const cp = session.counterparts?.find((c) => c.id === speaker);
    if (cp?.role) return shortRole(cp.role);
    const sh = session.stakeholders?.find((s) => s.id === speaker);
    if (sh?.role) return `${shortRole(sh.role)} (Stakeholder)`;
  }
  return "Counterpart";
}

function appendReply(lines: Line[], chunk: string, speaker?: string): Line[] {
  const last = lines.at(-1);
  if (last?.role === "character") return [...lines.slice(0, -1), { ...last, text: last.text + chunk, speaker: last.speaker ?? speaker }];
  return [...lines, { role: "character", text: chunk, speaker }];
}

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export function Play() {
  const { id } = useParams() as { id: string };
  const me = useMe();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showOnboarding, setShowOnboarding] = useState(() => searchParams.get("onboard") === "1");
  const { data: session, error, reload } = useLoad<S["SessionOut"]>(`sessions/${id}`);
  const [live, setLive] = useState<Line[]>([]); // the turn in flight, until the saved transcript replaces it
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [unsynced, setUnsynced] = useState(false); // a saved turn the reload failed to show: the composer stays closed
  const [problem, setProblem] = useState<string>();
  const [turns, setTurns] = useState(0); // tells the playtest panel to refresh
  const [selectedInterlocutor, setSelectedInterlocutor] = useState<string | null>(null);
  const navigate = useNavigate();
  const known = useRef(0); // the highest turn number seen, even when a reload failed to show it
  const alive = useRef(true);
  const bottom = useRef<HTMLDivElement>(null);

  const activeInterlocutor =
    selectedInterlocutor ||
    session?.active_interlocutor ||
    session?.counterparts?.[0]?.id ||
    "counterpart";

  const handleSwitchInterlocutor = async (targetId: string) => {
    if (busy || unsynced) return;
    setSelectedInterlocutor(targetId);
    try {
      await api(`sessions/${id}/interlocutor`, { method: "POST", body: { interlocutor: targetId } });
      await reload();
    } catch {
    }
  };

  const [timeUp, setTimeUp] = useState(false); // the clock reached zero in this browser
  const [secondsIdle, setSecondsIdle] = useState(0);
  const silenceAfter = session?.silence_seconds ?? 90; // the scenario's own wait before the counterpart speaks up
  const triggerSilenceNudgeRef = useRef<() => Promise<void>>(() => Promise.resolve());

  const prepHidden = hidePrep();
  const [prepDismissed, setPrepDismissed] = useState(false);
  const [prepActive, setPrepActive] = useState(false);
  const [showPrepDrawer, setShowPrepDrawer] = useState(false);
  const [showGlossary, setShowGlossary] = useState(false);

  const needsPreparation =
    prepActive &&
    !prepDismissed &&
    session?.status === "active" &&
    session.turn === 0 &&
    session.mode !== "playtest" &&
    (session.preparation_modules?.length ?? 0) > 0;

  const handleSavePrep = async (data: Record<string, unknown>) => {
    try {
      await api(`sessions/${id}/preparation`, { method: "PUT", body: data });
      await reload();
      setPrepDismissed(true);
      setPrepActive(false);
      setShowPrepDrawer(false);
    } catch (failure) {
      setProblem((failure as Error).message);
      throw failure;
    }
  };

  const handleSkipPrep = async () => {
    try {
      await api(`sessions/${id}/preparation`, { method: "PUT", body: { skipped: true } });
      await reload();
    } catch (failure) {
      setProblem((failure as Error).message);
    } finally {
      setPrepDismissed(true);
      setPrepActive(false);
      setShowPrepDrawer(false);
    }
  };

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
    setPrepActive(false);
    setPrepDismissed(true);
    if (searchParams.get("onboard")) {
      setSearchParams({}, { replace: true });
    }
  };

  const handleOnboardingPrepare = () => {
    setShowOnboarding(false);
    setPrepActive(true);
    if (searchParams.get("onboard")) {
      setSearchParams({}, { replace: true });
    }
  };

  const handleOnboardingClose = () => {
    setShowOnboarding(false);
    setPrepActive(false);
    setPrepDismissed(true);
    if (searchParams.get("onboard")) {
      setSearchParams({}, { replace: true });
    }
  };
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false; // stop waiting for a turn's outcome once the page is gone
    };
  }, []);
  useEffect(() => {
    known.current = 0; // a different session in place: its turns start from their own numbers
  }, [id]);

  useEffect(() => {
    if (busy || session?.status !== "active") {
      setSecondsIdle(0);
      return;
    }
    if (showOnboarding || needsPreparation) {
      return;
    }
    const interval = setInterval(() => {
      setSecondsIdle((s) => s + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [busy, showOnboarding, needsPreparation, session?.status]);

  useEffect(() => {
    if (secondsIdle >= silenceAfter && !busy && !showOnboarding && !needsPreparation && session?.status === "active") {
      setSecondsIdle(0);
      void triggerSilenceNudgeRef.current();
    }
  }, [secondsIdle, silenceAfter, busy, showOnboarding, session?.status]);

  // A scenario whose rules end the meeting at the time limit: ask the server to end it once no turn is running. The
  // server checks its own clock, so a refusal (a clock that ran fast, a turn still running) is simply ignored.
  useEffect(() => {
    if (!timeUp || busy || session?.status !== "active" || !session.on_timeout || session.on_timeout === "guide") return;
    setTimeUp(false);
    void api(`sessions/${id}/time-up`, { method: "POST" }).catch(() => {}).finally(() => void reload());
  }, [timeUp, busy, session?.status, session?.on_timeout, id, reload]);

  const lines: Line[] = [...(session?.transcript ?? []), ...live];
  const tail = lines.at(-1)?.text;
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [lines.length, tail]);

  if (!session) return error ? <Problem text={error} /> : <p className="loading">Loading…</p>;

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const mine = text.trim();
    if (!mine || busy) return;
    const turnBefore = Math.max(session!.turn, known.current); // decided by the turn number, never by matching text
    let committed = false; // the turn reached the transcript, whatever fails afterwards
    setSecondsIdle(0);
    setBusy(true);
    setProblem(undefined);
    setText("");
    setLive([{ role: "trainee", text: mine }]);
    try {
      let done = false; // the stream's terminal event arrived: the turn is committed, whatever fails afterwards
      let refused: string | null = null; // the server refused (a non-OK response or an error event): nothing was saved
      try {
        for await (const { event: kind, data } of sendTurn(id, mine, activeInterlocutor)) {
          if (kind === "reply") setLive((current) => appendReply(current, data.text, activeInterlocutor));
          else if (kind === "notice") setLive((current) => [...current, { role: "notice", text: data.detail }]);
          else if (kind === "done") {
            done = true;
            known.current = Math.max(known.current, data.turn);
          }
          else if (kind === "error") refused = data.detail;
        }
      } catch (failure) {
        if (failure instanceof ApiError) refused = failure.message; // a non-OK response, before the stream
        // any other failure is ambiguous: the turn may or may not be committed
      }
      committed = done;
      if (!done) {
        if (refused !== null) {
          setProblem(refused);
          setText(mine); // nothing was saved: let the trainee send it again
        } else {
          // EOF or a transport failure: the server may still be running the turn. Wait for it, then decide by turn number.
          try {
            const deadline = Date.now() + 200_000; // a running turn gets 200 s to settle
            let fresh = await api<S["SessionOut"]>(`sessions/${id}`);
            known.current = Math.max(known.current, fresh.turn);
            while (
              fresh.turn_running &&
              fresh.status === "active" && // an ended session is never "running": the finisher's claim is not a turn
              fresh.turn <= turnBefore && // the outcome is already known: stop waiting
              Date.now() < deadline &&
              alive.current
            ) {
              setProblem("Checking whether your message was saved…");
              await delay(2000); // one request at a time: the next poll starts only after this one settled
              if (!alive.current) break;
              try {
                fresh = await api<S["SessionOut"]>(`sessions/${id}`);
                known.current = Math.max(known.current, fresh.turn);
              } catch (failure) {
                if (failure instanceof ApiError) throw failure; // a server answer ends the wait
                // a transient network failure on the same flaky link: keep polling until the deadline
              }
            }
            if (fresh.turn > turnBefore) {
              committed = true; // the turn committed after all: the reload below shows it, and the composer stays empty
              setProblem(undefined); // the "Checking…" note ends here
            } else if (fresh.turn_running && fresh.status === "active") {
              // the deadline passed while the turn may still commit: nothing is certain
              setProblem("We could not confirm whether your message was saved. Reload the page before sending it again.");
              setText(mine);
            } else {
              setProblem("The connection dropped before the turn finished. Nothing was saved; send it again.");
              setText(mine);
            }
          } catch {
            setProblem(
              "The connection dropped and we could not check whether your message was saved. Reload the page before sending it again.",
            );
            setText(mine);
          }
        }
      }
    } finally {
      const fresh = await reload(); // never throws: useLoad turns failures into state
      if (fresh) {
        known.current = Math.max(known.current, fresh.turn);
        setUnsynced(false); // the saved transcript is on screen again
      } else if (committed) {
        setProblem("Your message was saved. Reload the page to continue.");
        setUnsynced(true);
      }
      if (fresh || !committed) setLive([]); // a committed turn stays on screen when the reload failed to show it
      setBusy(false);
      setTurns((count) => count + 1);
    }
  }

  async function triggerSilenceNudge() {
    if (busy || unsynced || session?.status !== "active") return;
    setSecondsIdle(0);
    setBusy(true);
    setProblem(undefined);
    setLive([{ role: "trainee", text: "(The delegate remains silent.)" }]);
    let committed = false;
    try {
      let done = false;
      let refused: string | null = null;
      try {
        for await (const { event: kind, data } of sendNudge(id)) {
          if (kind === "reply") setLive((current) => appendReply(current, data.text, activeInterlocutor));
          else if (kind === "notice") setLive((current) => [...current, { role: "notice", text: data.detail }]);
          else if (kind === "done") {
            done = true;
            known.current = Math.max(known.current, data.turn);
          } else if (kind === "error") refused = data.detail;
        }
      } catch (failure) {
        if (failure instanceof ApiError) refused = failure.message;
      }
      committed = done;
      if (!done && refused !== null) {
        setProblem(refused);
      }
    } finally {
      const fresh = await reload();
      if (fresh) {
        known.current = Math.max(known.current, fresh.turn);
        setUnsynced(false);
      } else if (committed) {
        setProblem("Silence was recorded. Reload the page to continue.");
        setUnsynced(true);
      }
      if (fresh || !committed) setLive([]);
      setBusy(false);
      setTurns((count) => count + 1);
    }
  }
  triggerSilenceNudgeRef.current = triggerSilenceNudge;

  async function finish() {
    if (!confirm("End the session and read your debrief?")) return;
    try {
      await api(`sessions/${id}/end`, { method: "POST" });
      navigate(`/sessions/${id}/debrief`);
    } catch (failure) {
      setProblem((failure as Error).message);
    }
  }

  const phases = session.phases?.length ? session.phases : DEFAULT_PHASES;
  const currentPhase = phases.find((item) => item.id === (session.phase || "").toLowerCase()) ?? phases[0];

  return (
    <div className={session.mode === "playtest" ? "play with-panel" : "play"}>
      {showOnboarding && (
        <OnboardingCarousel
          session={session}
          userName={me.display_name}
          onComplete={handleOnboardingComplete}
          onPrepare={prepHidden ? undefined : handleOnboardingPrepare}
          onClose={handleOnboardingClose}
        />
      )}
      {showGlossary && <GlossaryModal onClose={() => setShowGlossary(false)} />}
      {needsPreparation && (
        <PreparationView
          session={session}
          onSave={handleSavePrep}
          onSkip={handleSkipPrep}
          onClose={() => {
            setPrepDismissed(true);
            setPrepActive(false);
          }}
        />
      )}
      {showPrepDrawer && (
        <PreparationView
          session={session}
          onSave={handleSavePrep}
          onClose={() => setShowPrepDrawer(false)}
          isDrawer
        />
      )}
      <section>
        <div className="play-header-row">
          <h1>{session.title}</h1>
          <div className="play-header-actions">
            <button
              type="button"
              className="btn-onboard-trigger"
              onClick={() => setShowOnboarding(true)}
              title="Review your mission brief, facts, and objective"
            >
              <IconClipboard size={16} /> Brief & Objectives
            </button>
            <button
              type="button"
              className="btn-onboard-trigger"
              onClick={() => setShowGlossary(true)}
              title="Frontline negotiation terminology"
            >
              <IconBook size={16} /> Glossary
            </button>
            {!prepHidden && (session.preparation_modules?.length ?? 0) > 0 && (
              <button
                type="button"
                className="btn-onboard-trigger btn-prep-trigger"
                onClick={() => setShowPrepDrawer(true)}
                title="Open your Naivasha Grid preparation sheet"
              >
                <IconMap size={16} /> Prep Sheet
              </button>
            )}
          </div>
        </div>

        {/* Dynamic Negotiation Phase HUD */}
        <div className="phase-hud" role="region" aria-label="Negotiation Phase">
          <div className="phase-indicator-row">
            <div className="phase-badge-group">
              {phases.map((item) => {
                const isActive = item.id === currentPhase.id;
                return (
                  <span
                    key={item.id}
                    className={`phase-pill ${isActive ? "active" : "inactive"} phase-${item.id}`}
                    title={item.hint}
                  >
                    <span className="phase-dot" />
                    {item.label}
                  </span>
                );
              })}
            </div>
            <div className="phase-meta-turn">
              <span className="phase-turn-counter">Turn {session.turn}</span>
              {session.status === "active" && (
                <SessionClock
                  secondsLeft={session.seconds_left}
                  minutesTotal={session.minutes_total}
                  warnings={session.warning_minutes}
                  onTimeout={session.on_timeout}
                  onExpire={() => setTimeUp(true)}
                />
              )}
            </div>
          </div>
          {currentPhase.hint && <p className="phase-subtitle-text">{currentPhase.hint}</p>}
        </div>

        {/* Multi-Party & Network Play Interlocutor Switcher */}
        {((session.counterparts && session.counterparts.length > 1) || (session.stakeholders && session.stakeholders.length > 0)) && (
          <div className="interlocutor-channel-bar" role="region" aria-label="Interlocutor Channels">
            <span className="channel-bar-label">Speaking to:</span>
            <div className="channel-tabs-group">
              {(session.counterparts ?? []).map((cp) => {
                const isActive = activeInterlocutor === cp.id;
                return (
                  <button
                    key={cp.id}
                    type="button"
                    className={`channel-tab-btn counterpart-tab ${isActive ? "active" : ""}`}
                    onClick={() => void handleSwitchInterlocutor(cp.id)}
                    title={cp.stated_position || cp.persona || cp.role}
                  >
                    <span className="tab-icon"><IconShield size={16} /></span>
                    <span className="tab-label">{shortRole(cp.role) || cp.id}</span>
                  </button>
                );
              })}
              {(session.stakeholders ?? []).map((sh) => {
                const isActive = activeInterlocutor === sh.id;
                return (
                  <button
                    key={sh.id}
                    type="button"
                    className={`channel-tab-btn stakeholder-tab ${isActive ? "active" : ""}`}
                    onClick={() => void handleSwitchInterlocutor(sh.id)}
                    title={`Stakeholder (${sh.influence || "medium"} influence)`}
                  >
                    <span className="tab-icon"><IconGlobe size={16} /></span>
                    <span className="tab-label">{shortRole(sh.role) || sh.id}</span>
                    <span className="stakeholder-tag">Stakeholder</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="dialogue-container">
          <ol className="transcript">
            {lines.map((line, index) => {
              const isSilence = line.text.startsWith("(") && line.text.endsWith(")");
              return (
                <li key={index} className={`${line.role}${isSilence ? " silence-turn" : ""}`}>
                  <span className="who">{getSpeakerLabel(line, session)}</span>
                  <span className={isSilence ? "italic-note" : ""}>{line.text}</span>
                </li>
              );
            })}
            <div ref={bottom} />
          </ol>
          <Problem text={problem ?? error} />
          {session.status === "ended" ? (
            <p className="outcome">
              Session ended{session.outcome ? `: ${session.outcome.label}` : ""}.{" "}
              <Link to={`/sessions/${id}/debrief`}>Read the debrief</Link>
            </p>
          ) : (
            <div className="dialogue-footer">
              {secondsIdle >= Math.floor(silenceAfter / 2) && session.status === "active" && !busy && (
                <div className="silence-bar" role="alert">
                  <div className="silence-msg">
                    <span className="silence-icon"><IconHourglass size={16} /></span>
                    <span>Counterpart waiting ({Math.max(0, silenceAfter - secondsIdle)}s remaining)</span>
                  </div>
                  <button
                    type="button"
                    className="btn-silence"
                    onClick={() => void triggerSilenceNudge()}
                    title="Pass your turn in silence"
                  >
                    Remain silent
                  </button>
                </div>
              )}
              <form onSubmit={send} className="composer">
                <textarea
                  aria-label="Your message"
                  value={text}
                  rows={3}
                  maxLength={4000}
                  disabled={busy || unsynced} // closed while a saved turn is not on screen: with nothing typed, Send cannot fire
                  onChange={(event) => {
                    setText(event.target.value);
                    setSecondsIdle(0);
                  }}
                  onKeyDown={(event) => {
                    setSecondsIdle(0);
                    if (event.nativeEvent.isComposing || event.keyCode === 229) return; // an Enter accepting an IME candidate is not a send
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                />
                <button disabled={busy || !text.trim()}>Send</button>
                <button type="button" className="secondary" onClick={finish} disabled={busy}>
                  End session
                </button>
              </form>
            </div>
          )}
        </div>
      </section>
      {session.mode === "playtest" && <PlaytestConsole sessionId={id} turns={turns} />}
    </div>
  );
}

/** Playtest only: the same console the trainer steers with, plus a way into the full trainer view. */
function PlaytestConsole({ sessionId, turns }: { sessionId: string; turns: number }) {
  const { data, error, reload } = useProgress(sessionId);
  useEffect(() => {
    if (turns > 0) void reload();
  }, [turns, reload]);
  if (!data) return <aside className="console">{error && <Problem text={error} />}</aside>;
  return (
    <div>
      <p>
        <Link to={`/sessions/${sessionId}/watch`}>Open trainer view</Link>
      </p>
      <Console
        view={viewOf(data)}
        sessionId={sessionId}
        onChange={async () => {
          await reload();
        }}
      />
    </div>
  );
}
