import { useMemo, useState } from "react";
import type { TrainerView } from "./progress";

interface ObserverSheetProps {
  view: TrainerView;
  sessionId: string;
}

export function ObserverSheet({ view, sessionId }: ObserverSheetProps) {
  const transcript = view.state.history || [];

  const { traineeWords, counterpartWords, traineeTurns, counterpartTurns } = useMemo(() => {
    let tWords = 0;
    let cWords = 0;
    let tTurns = 0;
    let cTurns = 0;

    for (const msg of transcript) {
      const words = msg.text.trim().split(/\s+/).filter(Boolean).length;
      if (msg.role === "trainee") {
        tWords += words;
        tTurns += 1;
      } else {
        cWords += words;
        cTurns += 1;
      }
    }
    return {
      traineeWords: tWords,
      counterpartWords: cWords,
      traineeTurns: tTurns,
      counterpartTurns: cTurns,
    };
  }, [transcript]);

  const totalWords = traineeWords + counterpartWords;
  const traineePct = totalWords > 0 ? Math.round((traineeWords / totalWords) * 100) : 50;
  const counterpartPct = totalWords > 0 ? 100 - traineePct : 50;

  // 6 De-escalation Steps observer state
  const [observedSteps, setObservedSteps] = useState<Record<number, boolean>>({});
  const [notes, setNotes] = useState(() => {
    try {
      return localStorage.getItem(`trainer_observer_notes_${sessionId}`) || "";
    } catch {
      return "";
    }
  });

  const handleToggleStep = (stepNum: number) => {
    setObservedSteps((prev) => ({ ...prev, [stepNum]: !prev[stepNum] }));
  };

  const handleNotesChange = (val: string) => {
    setNotes(val);
    try {
      localStorage.setItem(`trainer_observer_notes_${sessionId}`, val);
    } catch {
      // storage unavailable
    }
  };

  const DEESCALATION_STEPS = [
    {
      num: 1,
      title: "1. Pause & acknowledge emotion",
      description: "Did the trainee pause rather than defend, explicitly noting the counterpart's tension or concern?",
    },
    {
      num: 2,
      title: "2. Reformulate & clarify facts",
      description: "Did the trainee repeat back what they heard to verify accuracy and signal active listening?",
    },
    {
      num: 3,
      title: "3. Validate dignity & institutional role",
      description: "Did the trainee respect the counterpart's authority, responsibility, and operational constraints?",
    },
    {
      num: 4,
      title: "4. Shift to shared common ground",
      description: "Did the trainee anchor discussions on the Island of Agreements (shared facts, mutual security)?",
    },
    {
      num: 5,
      title: "5. Propose constructive, reciprocal step",
      description: "Did the trainee suggest a concrete, balanced next move rather than demanding unilateral compliance?",
    },
    {
      num: 6,
      title: "6. Establish joint monitoring & follow-up",
      description: "Did the trainee define clear verification modalities, point of contact, and timeline?",
    },
  ];

  return (
    <div className="observer-sheet-panel">
      {/* Speaker Balance: Who is Talking */}
      <section className="card">
        <div className="eyebrow">Observer metric · Communication balance</div>
        <h2>Who is Talking?</h2>
        <p className="lead-text">
          Effective frontline negotiators avoid dominating the conversation. The counterpart should do 50–60% of the talking.
        </p>

        <div className="speaker-balance-box">
          <div className="balance-bar-wrapper">
            <div className="balance-bar">
              <div
                className="balance-fill trainee"
                style={{ width: `${traineePct}%` }}
                title={`Trainee: ${traineePct}%`}
              />
              <div
                className="balance-fill counterpart"
                style={{ width: `${counterpartPct}%` }}
                title={`Counterpart: ${counterpartPct}%`}
              />
            </div>
          </div>

          <div className="speaker-stats-grid">
            <div className="speaker-stat-col trainee">
              <span className="speaker-badge">TRAINEE</span>
              <span className="speaker-metric">{traineePct}%</span>
              <small>{traineeWords} words · {traineeTurns} messages</small>
            </div>
            <div className="speaker-stat-col counterpart">
              <span className="speaker-badge">COUNTERPART</span>
              <span className="speaker-metric">{counterpartPct}%</span>
              <small>{counterpartWords} words · {counterpartTurns} messages</small>
            </div>
          </div>
        </div>
      </section>

      {/* Who Decides & Who Diverts */}
      <div className="observer-two-col">
        {/* Who Decides */}
        <section className="card">
          <div className="eyebrow">Mandate & Authority</div>
          <h2>Who Decides?</h2>
          <p className="hint">
            Watch whether the trainee stays within their mandate and whether the counterpart has authentic decision authority.
          </p>

          <div className="authority-check-list">
            <div className="authority-check-item">
              <strong>Trainee Mandate Check:</strong>
              <p>Did the trainee commit only to items authorized under local mandate, and refer headquarters items?</p>
            </div>
            <div className="authority-check-item">
              <strong>Counterpart Power Signals:</strong>
              <p>Does the counterpart claim direct command, or are they bound by invisible higher-ups?</p>
            </div>
            <div className="authority-check-item">
              <strong>Bottom Line Holding:</strong>
              <p>Did the trainee hold fast against pressure to concede on non-negotiable red lines?</p>
            </div>
          </div>
        </section>

        {/* Who Diverts */}
        <section className="card">
          <div className="eyebrow">Dialogue Dynamics (Tool 4)</div>
          <h2>Who Diverts?</h2>
          <p className="hint">
            Monitor topic and level shifts. Watch who pulls the conversation into politics or legal formalism.
          </p>

          <div className="divert-indicators-list">
            <div className="divert-item">
              <span className="level-badge technical">Technical</span>
              <p>Passage modalities, convoy manifests, vehicle markings, timing, and inspection procedures.</p>
            </div>
            <div className="divert-item">
              <span className="level-badge legal">Legal</span>
              <p>National sovereignty, legal jurisdiction, bilateral accords, and ministerial authorizations.</p>
            </div>
            <div className="divert-item">
              <span className="level-badge political">Political</span>
              <p>War blame, political accusations, foreign interference claims, and loyalty tests.</p>
            </div>
          </div>
        </section>
      </div>

      {/* De-escalation Checklist (FH Session 13) */}
      <section className="card">
        <div className="eyebrow">Facilitator's Handbook Session 13</div>
        <h2>6-Step De-escalation Protocol Checklist</h2>
        <p className="hint">
          Check off the steps observed during simulated tension spikes and hostility peaks.
        </p>

        <div className="deescalation-checklist">
          {DEESCALATION_STEPS.map((step) => (
            <label key={step.num} className={`deescalation-step-row ${observedSteps[step.num] ? "observed" : ""}`}>
              <input
                type="checkbox"
                checked={!!observedSteps[step.num]}
                onChange={() => handleToggleStep(step.num)}
                aria-label={step.title}
              />
              <div className="step-content">
                <strong>{step.title}</strong>
                <p>{step.description}</p>
              </div>
            </label>
          ))}
        </div>
      </section>

      {/* Trainer Observation Notes */}
      <section className="card">
        <div className="eyebrow">Live Observations</div>
        <h2>Observer Field Notes</h2>
        <label className="field">
          <span>Notes & verbatim quotes for the post-session debrief:</span>
          <textarea
            rows={5}
            value={notes}
            placeholder="Record key turning points, quotes, and de-escalation moments here..."
            onChange={(e) => handleNotesChange(e.target.value)}
          />
        </label>
      </section>
    </div>
  );
}
