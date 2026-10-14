import { Fragment, useState } from "react";
import type { S } from "../../api/client";
import { IconAlertTriangle, IconCheck, IconX } from "../../icons";

export interface OnboardingCarouselProps {
  session: S["SessionOut"];
  userName?: string;
  onComplete: () => void;
  onPrepare?: () => void;
  onClose?: () => void;
}

const SECTIONS = [
  { id: "mission", label: "Mission" },
  { id: "facts", label: "What we know" },
  { id: "objective", label: "Objective" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

interface ParsedBrief {
  situation: string;
  objective: string;
  facts: string[];
  redLines: string[];
  canDecide: string[];
  mustRefer: string[];
  counterpartRole: string;
  estimatedMinutes: number;
}

function parseBrief(brief: Record<string, unknown>, title: string): ParsedBrief {
  const situation = typeof brief.situation === "string" ? brief.situation.trim() : "";
  const objective = typeof brief.objective === "string" ? brief.objective.trim() : `Negotiate access under acceptable modalities for ${title}.`;

  // Parse counterpart role
  let counterpartRole = typeof brief.counterpart_role === "string" ? brief.counterpart_role : "";
  if (!counterpartRole) {
    const match = situation.match(/You are meeting\s+([^.]+)/i) || situation.match(/negotiate with\s+([^.]+)/i);
    counterpartRole = match ? match[1].trim() : "the designated counterpart";
  }

  // Parse estimated minutes
  const estimatedMinutes = typeof brief.estimated_minutes === "number" ? brief.estimated_minutes : 15;

  // Extract starting facts: prefer structured facts if present, otherwise extract from situation or fall back
  const facts: string[] = [];
  if (Array.isArray(brief.facts)) {
    for (const item of brief.facts) {
      if (typeof item === "string") facts.push(item);
    }
  }
  if (facts.length === 0 && situation.includes("What you know")) {
    const afterKnow = situation.split(/What you know[^:]*:/i)[1];
    if (afterKnow) {
      const parts = afterKnow.split(";").map((p) => p.trim()).filter(Boolean);
      for (const p of parts) {
        facts.push(p.replace(/^[•\-\s]+/, ""));
      }
    }
  }

  // Fallback facts if not specifically parsed
  if (facts.length === 0 && situation) {
    const sentences = situation.split(/(?<=[.?!])\s+/).filter((s) => s.length > 20);
    facts.push(...sentences.slice(0, 4));
  }

  // Clean situation for display (strip legacy "What you know..." appendix if present)
  const cleanSituation = situation.replace(/\s*What you know\s*\(?[^:]*\)?:\s*[\s\S]*$/i, "").trim();

  // Parse red lines
  const redLines: string[] = [];
  if (Array.isArray(brief.red_lines)) {
    for (const item of brief.red_lines) {
      if (typeof item === "string") redLines.push(item);
      else if (item && typeof item === "object" && "text" in item && typeof (item as { text: unknown }).text === "string") {
        redLines.push((item as { text: string }).text);
      }
    }
  }

  // Parse mandate
  const canDecide: string[] = [];
  const mustRefer: string[] = [];
  if (brief.mandate && typeof brief.mandate === "object") {
    const m = brief.mandate as { can_decide?: unknown[]; must_refer?: unknown[] };
    if (Array.isArray(m.can_decide)) {
      canDecide.push(...m.can_decide.filter((s): s is string => typeof s === "string"));
    }
    if (Array.isArray(m.must_refer)) {
      mustRefer.push(...m.must_refer.filter((s): s is string => typeof s === "string"));
    }
  }

  return {
    situation: cleanSituation || situation,
    objective,
    facts,
    redLines,
    canDecide,
    mustRefer,
    counterpartRole,
    estimatedMinutes,
  };
}

export function OnboardingCarousel({ session, onComplete, onPrepare, onClose }: OnboardingCarouselProps) {
  const [section, setSection] = useState<SectionId>("mission");
  const parsed = parseBrief(session.brief as Record<string, unknown>, session.title);
  const activeIndex = SECTIONS.findIndex((item) => item.id === section);
  // A dialogue already under way: this dialog is a brief recheck, not an onboarding
  const revisit = session.turn > 0;
  const last = section === "objective";

  function handleDone() {
    if (revisit) {
      (onClose ?? onComplete)();
      return;
    }
    try {
      sessionStorage.setItem(`cross_onboarded_${session.id}`, "done");
    } catch {
      // storage unavailable
    }
    onComplete();
  }

  function close() {
    (onClose ?? handleDone)();
  }

  return (
    <div className="onboard-overlay" role="dialog" aria-modal="true" aria-label="Simulation Onboarding">
      <div className="onboard-card">
        <button type="button" className="close-button onboard-close" onClick={close} aria-label="Close brief">
          <IconX size={16} />
        </button>
        {/* Brief sections: pick any part at any time */}
        <nav className="onboard-section-nav" aria-label="Brief sections">
          {SECTIONS.map((item, index) => (
            <Fragment key={item.id}>
              {index > 0 && (
                <span
                  className={`onboard-nav-line ${index <= activeIndex ? "done" : ""}`}
                  aria-hidden="true"
                />
              )}
              <button
                type="button"
                className={`onboard-section-tab ${index <= activeIndex ? "active" : ""}`}
                aria-current={section === item.id ? "true" : undefined}
                onClick={() => setSection(item.id)}
              >
                {item.label}
              </button>
            </Fragment>
          ))}
        </nav>

        {/* Mission */}
        {section === "mission" && (
          <div className="onboard-step step-mission">
            <div className="onboard-eyebrow">YOUR MISSION</div>
            <h2>{session.title}</h2>
            <p className="lead-text">{parsed.situation || parsed.objective}</p>

            <div className="stats-box">
              <div className="stat-col">
                <span className="stat-label">EXERCISE</span>
                <span className="stat-value">{session.title}</span>
              </div>
              <div className="stat-col">
                <span className="stat-label">LENGTH</span>
                <span className="stat-value">{parsed.estimatedMinutes}:00</span>
              </div>
              <div className="stat-col">
                <span className="stat-label">FORMAT</span>
                <span className="stat-value">Written exchange</span>
              </div>
            </div>

            {(parsed.canDecide.length > 0 || parsed.mustRefer.length > 0) && (
              <div className="mandate-grid">
                {parsed.canDecide.length > 0 && (
                  <div className="mandate-col can-decide">
                    <span className="mandate-title"><IconCheck size={14} /> Authorized within your mandate</span>
                    <ul>
                      {parsed.canDecide.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {parsed.mustRefer.length > 0 && (
                  <div className="mandate-col must-refer">
                    <span className="mandate-title"><IconAlertTriangle size={14} /> Requires headquarters referral</span>
                    <ul>
                      {parsed.mustRefer.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* What we know */}
        {section === "facts" && (
          <div className="onboard-step step-facts">
            <div className="onboard-eyebrow">WHAT YOU KNOW</div>
            <h2>The facts you start with</h2>

            <ul className="facts-list">
              {parsed.facts.map((fact, idx) => (
                <li key={idx}>
                  <span className="bullet-dash">—</span>
                  <span>{fact}</span>
                </li>
              ))}
            </ul>

            {parsed.redLines.length > 0 && (
              <div className="boundaries-box">
                <span className="boundaries-title">RED LINES (NON-NEGOTIABLE)</span>
                <ul>
                  {parsed.redLines.map((line, idx) => (
                    <li key={idx}><IconX size={12} /> {line}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Objective */}
        {section === "objective" && (
          <div className="onboard-step step-objective">
            <div className="onboard-eyebrow">YOUR OBJECTIVE</div>

            <div className="objective-callout">
              <p className="objective-text">{parsed.objective}</p>
            </div>

            <p className="objective-details">
              Counterpart: <strong>{parsed.counterpartRole}</strong>. You have approximately{" "}
              <strong>{parsed.estimatedMinutes}:00</strong>.
              How you get there matters as much as whether you do — your feedback covers both.
            </p>

            {onPrepare && (session.preparation_modules?.length ?? 0) > 0 && (
              <div className="onboard-actions single-action">
                <button
                  type="button"
                  className="button secondary"
                  onClick={onPrepare}
                >
                  Prepare Strategy (Naivasha Grid) →
                </button>
              </div>
            )}
          </div>
        )}

        <div className={`onboard-actions ${section === "mission" ? "single-action" : "split-actions"}`}>
          {section !== "mission" && (
            <button
              type="button"
              className="button secondary"
              onClick={() => setSection(section === "objective" ? "facts" : "mission")}
            >
              ← Back
            </button>
          )}
          <button
            type="button"
            className="btn-onboard-primary enter-btn"
            onClick={last ? handleDone : () => setSection(section === "mission" ? "facts" : "objective")}
          >
            {last ? (revisit ? "Close" : "Enter Negotiation →") : "Next →"}
          </button>
        </div>

        {!revisit && onClose && section !== "objective" && (
          <button
            type="button"
            className="onboard-skip-link"
            onClick={onClose}
          >
            Skip to negotiation
          </button>
        )}
      </div>
    </div>
  );
}
