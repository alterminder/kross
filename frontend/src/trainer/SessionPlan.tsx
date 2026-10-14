import type { TrainerView } from "./progress";
import { IconAlertTriangle, IconCheck } from "../icons";

interface SessionPlanProps {
  view: TrainerView;
  title: string;
}

export function SessionPlan({ view, title }: SessionPlanProps) {
  const stateRecord = view.state as unknown as Record<string, unknown>;
  const brief = (stateRecord.brief ?? {}) as Record<string, unknown>;
  const situation = typeof brief.situation === "string" ? brief.situation : "";
  const objective = typeof brief.objective === "string" ? brief.objective : `Negotiate access under principled humanitarian conditions with ${view.counterpart || "the counterpart"}.`;

  const mandate = (brief.mandate ?? {}) as { can_decide?: string[]; must_refer?: string[] };
  const canDecide = Array.isArray(mandate.can_decide) ? mandate.can_decide : [];
  const mustRefer = Array.isArray(mandate.must_refer) ? mandate.must_refer : [];

  return (
    <div className="session-plan-panel">
      {/* Facilitator Learning Objectives */}
      <section className="card">
        <div className="eyebrow">Facilitator's Handbook · Learning Objectives</div>
        <h2>Session Plan: {title}</h2>
        <p className="lead-text">
          Standard session outline based on the CCHN Facilitator's Handbook (FH). Ground the simulation in clear participant capabilities.
        </p>

        <div className="plan-objectives-box">
          <span className="objectives-badge">PARTICIPANTS ARE ABLE TO:</span>
          <ul className="plan-objectives-list">
            <li>
              <strong>Establish & Maintain Dialogue:</strong> Initiate constructive frontline dialogue with the counterpart while upholding core red lines and organizational principles.
            </li>
            <li>
              <strong>Navigate the Iceberg:</strong> Probe beyond stated demands to uncover tactical reasoning, institutional constraints, and deep values.
            </li>
            <li>
              <strong>Manage Conversation Levels:</strong> Identify and redirect dialogue movements between Technical, Legal, and Political levels (CCHN Tool 4).
            </li>
            <li>
              <strong>Apply De-escalation Protocol:</strong> De-escalate interpersonal hostility spikes using the 6-step communication cycle (FH Session 13).
            </li>
            <li>
              <strong>Secure Viable Terms:</strong> Consolidate terms within the Common Shared Space (CSS) without compromising critical mandate boundaries.
            </li>
          </ul>
        </div>
      </section>

      {/* Brief Reading & Operational Context */}
      <section className="card">
        <div className="eyebrow">Participant Brief Reading & Context</div>
        <h2>Operational Context</h2>
        <div className="plan-context-grid">
          <div className="context-item">
            <h4>Situation Overview</h4>
            <p>{situation || "Frontline humanitarian operational challenge."}</p>
          </div>
          <div className="context-item">
            <h4>Primary Objective</h4>
            <p>{objective}</p>
          </div>
        </div>

        {(canDecide.length > 0 || mustRefer.length > 0) && (
          <div className="mandate-summary-grid">
            {canDecide.length > 0 && (
              <div className="mandate-col can-decide">
                <span className="mandate-title"><IconCheck size={14} /> Authorized within Mandate</span>
                <ul>
                  {canDecide.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {mustRefer.length > 0 && (
              <div className="mandate-col must-refer">
                <span className="mandate-title"><IconAlertTriangle size={14} /> Requires HQ Referral</span>
                <ul>
                  {mustRefer.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 4-Phase Simulation Protocol */}
      <section className="card">
        <div className="eyebrow">Simulation Architecture</div>
        <h2>4-Phase Exercise Protocol</h2>
        <div className="simulation-phases-grid">
          <div className="sim-phase-card">
            <span className="phase-num">PHASE 1</span>
            <h4>Preparation & Framing</h4>
            <p>
              Trainee conducts Naivasha Grid assessment: mandate limits, known facts, convergent norms, and counterpart legitimacy.
            </p>
          </div>
          <div className="sim-phase-card">
            <span className="phase-num">PHASE 2</span>
            <h4>Opening & Tone Setting</h4>
            <p>
              Greeting, active listening, and anchoring at the technical level. Avoiding immediate confrontation or premature concessions.
            </p>
          </div>
          <div className="sim-phase-card">
            <span className="phase-num">PHASE 3</span>
            <h4>Exploration & Tension</h4>
            <p>
              Counterpart challenges authority or raises demands. Trainer can inject tension signals. Trainee applies the 6-step de-escalation cycle.
            </p>
          </div>
          <div className="sim-phase-card">
            <span className="phase-num">PHASE 4</span>
            <h4>Closure & Terms Sheet</h4>
            <p>
              Drafting reciprocal terms, parking unresolved tier-3 issues, verifying clear roles, and confirming next steps.
            </p>
          </div>
        </div>
      </section>

      {/* Guided Debrief Prompts */}
      <section className="card">
        <div className="eyebrow">Facilitator debrief prompts</div>
        <h2>Debrief Reflection Questions (CCHN Grounded)</h2>
        <div className="debrief-prompts-list">
          <div className="prompt-item">
            <span className="tool-pill">CCHN Tool 4: Typology</span>
            <p className="prompt-q">"At what dialogue level (Technical, Legal, Political) did the conversation start, and did you notice when the counterpart attempted to shift levels?"</p>
          </div>
          <div className="prompt-item">
            <span className="tool-pill">CCHN Tool 8: De-escalation</span>
            <p className="prompt-q">"When the counterpart raised tension or questioned your presence, what was your immediate reaction? Did you pause and acknowledge emotion before presenting arguments?"</p>
          </div>
          <div className="prompt-item">
            <span className="tool-pill">CCHN Tool 9: Iceberg</span>
            <p className="prompt-q">"What underlying interests or institutional constraints were hidden beneath the counterpart's initial demands, and how did you uncover them?"</p>
          </div>
          <div className="prompt-item">
            <span className="tool-pill">CCHN Tool 13: Shared Benefit</span>
            <p className="prompt-q">"How did you present your proposal in terms of mutual interest rather than a unilateral humanitarian concession?"</p>
          </div>
          <div className="prompt-item">
            <span className="tool-pill">CCHN Tool 17: Red Lines</span>
            <p className="prompt-q">"Were any red lines tested? How did you signal non-negotiability without terminating the relationship?"</p>
          </div>
        </div>
      </section>
    </div>
  );
}
