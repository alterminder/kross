import { useEffect, useState } from "react";
import type { S } from "../../api/client";
import { IconClock, IconX } from "../../icons";

export interface PreparationViewProps {
  session: S["SessionOut"];
  onSave: (data: Record<string, unknown>) => Promise<void> | void;
  onSkip?: () => Promise<void> | void;
  onClose?: () => void;
  isDrawer?: boolean;
}

export const MODULE_LABELS: Record<string, { title: string; tool: string; description: string }> = {
  island_of_agreements: {
    title: "Island of Agreements",
    tool: "CCHN Tool 2",
    description: "Map facts and norms into agreed, contested, convergent, and divergent ground.",
  },
  level_and_narrative: {
    title: "Level & Narrative",
    tool: "CCHN Tools 4 & 10",
    description: "Structure your own iceberg (WHY / HOW / WHAT) and your expected dialogue level.",
  },
  lines_and_options: {
    title: "Lines & Options",
    tool: "CCHN Tools 13 & 14",
    description: "Define your ideal outcome, bottom line, movable concessions, and tier sequencing plan.",
  },
  information_quality: {
    title: "Information Quality",
    tool: "CCHN Tool 1",
    description: "Assess available claims on source, method, fact-checking, and operational relevance.",
  },
  legitimacy_profile: {
    title: "Legitimacy Profile",
    tool: "CCHN Tool 3",
    description: "Identify which sources of legitimacy (legal, institutional, professional, moral) to emphasize.",
  },
  counterpart_iceberg: {
    title: "Counterpart Iceberg",
    tool: "CCHN Tool 9",
    description: "Anticipate the counterpart's stated position, tactical reasoning, and deep values.",
  },
  common_shared_space: {
    title: "Common Shared Space",
    tool: "CCHN Tool 11",
    description: "Identify common shared space between your humanitarian mandate and counterpart interests.",
  },
  network: {
    title: "Network Mapping",
    tool: "CCHN Tool 12",
    description: "Map influential stakeholders by their degree of influence and stance towards your mission.",
  },
  meeting_checklist: {
    title: "Meeting Checklist",
    tool: "CCHN Tool 6",
    description: "Review procedural conditions, counterpart authority, and conduct guidelines before meeting.",
  },
};

export function PreparationView({ session, onSave, onSkip, onClose, isDrawer = false }: PreparationViewProps) {
  const modules = session.preparation_modules?.length ? session.preparation_modules : ["island_of_agreements", "level_and_narrative", "lines_and_options"];
  const [activeModule, setActiveModule] = useState(modules[0]);
  const [saving, setSaving] = useState(false);

  // Existing or default state
  const prep = (session.preparation as Record<string, any>) || {};

  // Module 1: Island of Agreements
  const [agreedFacts, setAgreedFacts] = useState<string>(prep.island_of_agreements?.agreed_facts?.join("\n") || "");
  const [contestedFacts, setContestedFacts] = useState<string>(prep.island_of_agreements?.contested_facts?.join("\n") || "");
  const [convergentNorms, setConvergentNorms] = useState<string>(prep.island_of_agreements?.convergent_norms?.join("\n") || "");
  const [divergentNorms, setDivergentNorms] = useState<string>(prep.island_of_agreements?.divergent_norms?.join("\n") || "");

  // Module 2: Level & Narrative
  const [why, setWhy] = useState<string>(prep.level_and_narrative?.why || "");
  const [how, setHow] = useState<string>(prep.level_and_narrative?.how || "");
  const [what, setWhat] = useState<string>(prep.level_and_narrative?.what || "");
  const [expectedLevel, setExpectedLevel] = useState<string>(prep.level_and_narrative?.expected_level || "technical");

  // Module 3: Lines & Options
  const [idealOutcome, setIdealOutcome] = useState<string>(prep.lines_and_options?.ideal_outcome || "");
  const [bottomLine, setBottomLine] = useState<string>(prep.lines_and_options?.bottom_line || "");
  const [movablePieces, setMovablePieces] = useState<string>(prep.lines_and_options?.movable_pieces || "");
  const [counterpartBenefits, setCounterpartBenefits] = useState<string>(prep.lines_and_options?.counterpart_benefits || "");
  const [tierPlan, setTierPlan] = useState<string>(prep.lines_and_options?.tier_plan || "");

  // Module 4: Information Quality
  const [infoClaims, setInfoClaims] = useState<string>(prep.information_quality?.claims_assessment || "");

  // Module 5: Legitimacy Profile
  const [legitimacyEmphasis, setLegitimacyEmphasis] = useState<string[]>(prep.legitimacy_profile?.emphasis || ["professional", "institutional"]);

  // Module 6: Counterpart Iceberg
  const [cpPosition, setCpPosition] = useState<string>(prep.counterpart_iceberg?.position || "");
  const [cpReasoning, setCpReasoning] = useState<string>(prep.counterpart_iceberg?.tactical_reasoning || "");
  const [cpValues, setCpValues] = useState<string>(prep.counterpart_iceberg?.motives_values || "");

  // Module 7: Common Shared Space
  const [cssConvergent, setCssConvergent] = useState<string>(prep.common_shared_space?.convergent?.join("\n") || "");
  const [cssDivergent, setCssDivergent] = useState<string>(prep.common_shared_space?.divergent?.join("\n") || "");

  // Module 8: Network
  const [stakeholderSupportive, setStakeholderSupportive] = useState<string>(prep.network?.supportive || "");
  const [stakeholderOpposed, setStakeholderOpposed] = useState<string>(prep.network?.opposed || "");

  // Module 9: Meeting Checklist
  const [checklistNotes, setChecklistNotes] = useState<string>(prep.meeting_checklist?.notes || "");

  // Timer
  const [timeLeft, setTimeLeft] = useState<number | null>(() => {
    if (session.preparation_minutes && session.preparation_minutes > 0) {
      return session.preparation_minutes * 60;
    }
    return null;
  });

  useEffect(() => {
    if (timeLeft === null || timeLeft <= 0) return;
    const interval = setInterval(() => {
      setTimeLeft((t) => (t !== null && t > 0 ? t - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [timeLeft]);

  const parseLines = (text: string) =>
    text
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

  const [prepError, setPrepError] = useState<string | null>(null);

  const handleSave = async () => {
    setPrepError(null);
    setSaving(true);
    const data: Record<string, unknown> = {
      skipped: false,
      island_of_agreements: {
        agreed_facts: parseLines(agreedFacts),
        contested_facts: parseLines(contestedFacts),
        convergent_norms: parseLines(convergentNorms),
        divergent_norms: parseLines(divergentNorms),
      },
      level_and_narrative: {
        why,
        how,
        what,
        expected_level: expectedLevel,
      },
      lines_and_options: {
        ideal_outcome: idealOutcome,
        bottom_line: bottomLine,
        movable_pieces: movablePieces,
        counterpart_benefits: counterpartBenefits,
        tier_plan: tierPlan,
      },
    };

    if (modules.includes("information_quality")) {
      data.information_quality = { claims_assessment: infoClaims };
    }
    if (modules.includes("legitimacy_profile")) {
      data.legitimacy_profile = { emphasis: legitimacyEmphasis };
    }
    if (modules.includes("counterpart_iceberg")) {
      data.counterpart_iceberg = {
        position: cpPosition,
        tactical_reasoning: cpReasoning,
        motives_values: cpValues,
      };
    }
    if (modules.includes("common_shared_space")) {
      data.common_shared_space = {
        convergent: parseLines(cssConvergent),
        divergent: parseLines(cssDivergent),
      };
    }
    if (modules.includes("network")) {
      data.network = {
        supportive: stakeholderSupportive,
        opposed: stakeholderOpposed,
      };
    }
    if (modules.includes("meeting_checklist")) {
      data.meeting_checklist = { notes: checklistNotes };
    }

    try {
      await onSave(data);
    } catch (err) {
      setPrepError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    if (!onSkip) return;
    setPrepError(null);
    setSaving(true);
    try {
      await onSkip();
    } catch (err) {
      setPrepError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const toggleLegitimacy = (source: string) => {
    setLegitimacyEmphasis((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  const formatTimer = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  return (
    <div className={isDrawer ? "prep-drawer" : "onboard-overlay"} data-testid="preparation-view">
      <div className={isDrawer ? "prep-drawer-content" : "onboard-card prep-modal-card"}>
        <header className="prep-header">
          <div className="prep-title-block">
            <span className="onboard-eyebrow">STRATEGIC PREPARATION (NAIVASHA GRID)</span>
            <h2>{session.title || "Negotiation Planning"}</h2>
          </div>
          <div className="prep-header-right">
            {timeLeft !== null && (
              <span className={`prep-timer ${timeLeft < 60 ? "warning" : ""}`}>
                <IconClock size={15} /> {formatTimer(timeLeft)}
              </span>
            )}
            {onClose && (
              <button
                type="button"
                className="close-button"
                onClick={onClose}
                aria-label="Close preparation sheet"
              >
                <IconX size={16} />
              </button>
            )}
          </div>
        </header>

        {/* Module navigation tabs */}
        <nav className="prep-nav" aria-label="Preparation modules">
          {modules.map((mod) => (
            <button
              key={mod}
              type="button"
              className={`prep-nav-tab ${activeModule === mod ? "active" : ""}`}
              onClick={() => setActiveModule(mod)}
            >
              <span className="tab-title">{MODULE_LABELS[mod]?.title || mod}</span>
              <span className="tab-tool">{MODULE_LABELS[mod]?.tool}</span>
            </button>
          ))}
        </nav>

        {/* Active module content */}
        <div className="prep-module-container">
          <div className="prep-module-intro">
            <h3>{MODULE_LABELS[activeModule]?.title}</h3>
            <p className="quiet-note">{MODULE_LABELS[activeModule]?.description}</p>
          </div>

          {/* Module: Island of Agreements */}
          {activeModule === "island_of_agreements" && (
            <div className="prep-grid-4">
              <div className="prep-field">
                <label htmlFor="agreed-facts">
                  Agreed Facts
                  <span className="helper">Factual common ground</span>
                </label>
                <textarea
                  id="agreed-facts"
                  rows={4}
                  placeholder="One fact per line..."
                  value={agreedFacts}
                  onChange={(e) => setAgreedFacts(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="contested-facts">
                  Contested Facts
                  <span className="helper">Facts in dispute</span>
                </label>
                <textarea
                  id="contested-facts"
                  rows={4}
                  placeholder="One point per line..."
                  value={contestedFacts}
                  onChange={(e) => setContestedFacts(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="convergent-norms">
                  Convergent Norms
                  <span className="helper">Shared values & priorities</span>
                </label>
                <textarea
                  id="convergent-norms"
                  rows={4}
                  placeholder="Shared principles..."
                  value={convergentNorms}
                  onChange={(e) => setConvergentNorms(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="divergent-norms">
                  Divergent Norms
                  <span className="helper">Conflicting mandates & rules</span>
                </label>
                <textarea
                  id="divergent-norms"
                  rows={4}
                  placeholder="Friction points..."
                  value={divergentNorms}
                  onChange={(e) => setDivergentNorms(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Module: Level and Narrative */}
          {activeModule === "level_and_narrative" && (
            <div className="prep-stack">
              <div className="prep-field">
                <label htmlFor="own-why">
                  WHY (Identity & Core Humanitarian Principles)
                  <span className="helper">Why does your organization exist and operate here?</span>
                </label>
                <textarea
                  id="own-why"
                  rows={2}
                  placeholder="Humanity, impartiality, neutrality, operational independence..."
                  value={why}
                  onChange={(e) => setWhy(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="own-how">
                  HOW (Mandate, Policies & Modalities)
                  <span className="helper">How do you deliver aid, verify beneficiaries, and manage security?</span>
                </label>
                <textarea
                  id="own-how"
                  rows={2}
                  placeholder="Standard operating procedures, non-discrimination, direct distribution..."
                  value={how}
                  onChange={(e) => setHow(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="own-what">
                  WHAT (Specific Operational Transaction)
                  <span className="helper">What is the concrete convoy, clearance, or access requested?</span>
                </label>
                <textarea
                  id="own-what"
                  rows={2}
                  placeholder="Number of trucks, cargo details, dates, specific route..."
                  value={what}
                  onChange={(e) => setWhat(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="expected-level">Expected Negotiation Level (CCHN Tool 4)</label>
                <select
                  id="expected-level"
                  value={expectedLevel}
                  onChange={(e) => setExpectedLevel(e.target.value)}
                >
                  <option value="technical">Technical (Operational details, modalities, logistics)</option>
                  <option value="professional">Professional (Normative, institutional mandate, policy)</option>
                  <option value="political">Political (Strategic, high-level authority, legitimacy)</option>
                </select>
              </div>
            </div>
          )}

          {/* Module: Lines & Options */}
          {activeModule === "lines_and_options" && (
            <div className="prep-stack">
              <div className="prep-grid-2">
                <div className="prep-field">
                  <label htmlFor="ideal-outcome">
                    Ideal Outcome (Zone A)
                    <span className="helper">Best possible realistic agreement</span>
                  </label>
                  <textarea
                    id="ideal-outcome"
                    rows={2}
                    placeholder="Unconditional passage, full operational independence..."
                    value={idealOutcome}
                    onChange={(e) => setIdealOutcome(e.target.value)}
                  />
                </div>

                <div className="prep-field">
                  <label htmlFor="bottom-line">
                    Own Bottom Line (Zone B)
                    <span className="helper">Minimum acceptable before referring to mandator</span>
                  </label>
                  <textarea
                    id="bottom-line"
                    rows={2}
                    placeholder="E.g., No armed personnel on humanitarian vehicles..."
                    value={bottomLine}
                    onChange={(e) => setBottomLine(e.target.value)}
                  />
                </div>
              </div>

              <div className="prep-field">
                <label htmlFor="movable-pieces">
                  Movable Pieces & Trade-offs
                  <span className="helper">Terms you can adjust (timing, route, notification, sharing aggregate stats)</span>
                </label>
                <textarea
                  id="movable-pieces"
                  rows={2}
                  placeholder="Items to trade in exchange for red-line protection..."
                  value={movablePieces}
                  onChange={(e) => setMovablePieces(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="counterpart-benefits">
                  Benefits for Counterpart
                  <span className="helper">How this agreement serves the counterpart's interests</span>
                </label>
                <textarea
                  id="counterpart-benefits"
                  rows={2}
                  placeholder="Reduced local tension, credibility, orderly coordination..."
                  value={counterpartBenefits}
                  onChange={(e) => setCounterpartBenefits(e.target.value)}
                />
              </div>

              <div className="prep-field">
                <label htmlFor="tier-plan">
                  Tier Sequencing Strategy (CCHN Tool 14)
                  <span className="helper">Start with Tier 1 quick wins, leave Tier 3 difficult items for later</span>
                </label>
                <textarea
                  id="tier-plan"
                  rows={2}
                  placeholder="1. Agree convoy logistics -> 2. Incident protocol -> 3. Distribution custody..."
                  value={tierPlan}
                  onChange={(e) => setTierPlan(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Module: Information Quality */}
          {activeModule === "information_quality" && (
            <div className="prep-stack">
              <div className="prep-field">
                <label htmlFor="info-claims">
                  Claims Evaluation & Information Checks
                  <span className="helper">Evaluate key facts on Source (0-3), Method (0-3), Fact-checking (0-3), and Relevance (0-3)</span>
                </label>
                <textarea
                  id="info-claims"
                  rows={5}
                  placeholder="Record your assessment of security signals, checkpoint authority, and camp need figures..."
                  value={infoClaims}
                  onChange={(e) => setInfoClaims(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Module: Legitimacy Profile */}
          {activeModule === "legitimacy_profile" && (
            <div className="prep-stack">
              <label>Select Legitimacy Sources to Emphasize (CCHN Tool 3):</label>
              <div className="prep-checkbox-grid">
                {[
                  { id: "legal", label: "Legal Legitimacy", desc: "IHL, international humanitarian conventions, national laws" },
                  { id: "institutional", label: "Institutional Legitimacy", desc: "Organization track record, presence, established mandates" },
                  { id: "professional", label: "Professional Legitimacy", desc: "Technical competence, transparent protocols, neutrality" },
                  { id: "moral", label: "Moral / Ethical Legitimacy", desc: "Alleviating suffering, universal humanitarian values" },
                ].map((item) => (
                  <label key={item.id} className="prep-checkbox-card">
                    <input
                      type="checkbox"
                      checked={legitimacyEmphasis.includes(item.id)}
                      onChange={() => toggleLegitimacy(item.id)}
                    />
                    <div>
                      <strong>{item.label}</strong>
                      <p className="quiet-note">{item.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Module: Counterpart Iceberg */}
          {activeModule === "counterpart_iceberg" && (
            <div className="prep-stack">
              <div className="prep-field">
                <label htmlFor="cp-position">
                  Stated Position (What they demand upfront)
                </label>
                <textarea
                  id="cp-position"
                  rows={2}
                  placeholder="What is their public opening demand?"
                  value={cpPosition}
                  onChange={(e) => setCpPosition(e.target.value)}
                />
              </div>
              <div className="prep-field">
                <label htmlFor="cp-reasoning">
                  Tactical Reasoning (How they justify it & operational pressures)
                </label>
                <textarea
                  id="cp-reasoning"
                  rows={2}
                  placeholder="What operational concerns or pressures drive their stance?"
                  value={cpReasoning}
                  onChange={(e) => setCpReasoning(e.target.value)}
                />
              </div>
              <div className="prep-field">
                <label htmlFor="cp-values">
                  Deep Values & Motives (Why they care)
                </label>
                <textarea
                  id="cp-values"
                  rows={2}
                  placeholder="What underlying political, community, or dignity motives exist?"
                  value={cpValues}
                  onChange={(e) => setCpValues(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Module: Common Shared Space */}
          {activeModule === "common_shared_space" && (
            <div className="prep-grid-2">
              <div className="prep-field">
                <label htmlFor="css-convergent">
                  Convergent Elements (Common Shared Space)
                  <span className="helper">Areas where both parties' objectives overlap</span>
                </label>
                <textarea
                  id="css-convergent"
                  rows={5}
                  placeholder="Shared goals, preventing violence, orderly aid delivery..."
                  value={cssConvergent}
                  onChange={(e) => setCssConvergent(e.target.value)}
                />
              </div>
              <div className="prep-field">
                <label htmlFor="css-divergent">
                  Divergent Elements
                  <span className="helper">Areas of genuine friction</span>
                </label>
                <textarea
                  id="css-divergent"
                  rows={5}
                  placeholder="Armed escorts, custody of cargo, political statements..."
                  value={cssDivergent}
                  onChange={(e) => setCssDivergent(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Module: Network Mapping */}
          {activeModule === "network" && (
            <div className="prep-grid-2">
              <div className="prep-field">
                <label htmlFor="net-supportive">
                  Allies & Supportive Stakeholders
                  <span className="helper">Local leaders, camp representatives, cooperative commanders</span>
                </label>
                <textarea
                  id="net-supportive"
                  rows={4}
                  placeholder="Key contacts who can influence the counterpart positively..."
                  value={stakeholderSupportive}
                  onChange={(e) => setStakeholderSupportive(e.target.value)}
                />
              </div>
              <div className="prep-field">
                <label htmlFor="net-opposed">
                  Opposed or Constraining Stakeholders
                  <span className="helper">Hostile groups, hardline superiors, rival armed actors</span>
                </label>
                <textarea
                  id="net-opposed"
                  rows={4}
                  placeholder="Actors who limit the counterpart's leeway or demand bribes/escorts..."
                  value={stakeholderOpposed}
                  onChange={(e) => setStakeholderOpposed(e.target.value)}
                />
              </div>
            </div>
          )}

          {/* Module: Meeting Checklist */}
          {activeModule === "meeting_checklist" && (
            <div className="prep-stack">
              <div className="prep-field">
                <label htmlFor="checklist-notes">
                  Procedural Checklist & Conduct Notes
                  <span className="helper">Counterpart credentials, mandate limits, room setup, de-escalation posture</span>
                </label>
                <textarea
                  id="checklist-notes"
                  rows={5}
                  placeholder="Note key reminders: stay calm under pressure, avoid premature red lines, listen before proposing..."
                  value={checklistNotes}
                  onChange={(e) => setChecklistNotes(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>

        {prepError && (
          <div className="problem" style={{ margin: "16px 0 0" }} role="alert">
            {prepError}
          </div>
        )}

        {/* Action bar */}
        <footer className="prep-actions">
          {onSkip && (
            <button
              type="button"
              className="button secondary prep-skip-btn"
              onClick={handleSkip}
              disabled={saving}
            >
              Skip Preparation
            </button>
          )}

          <button
            type="button"
            className="btn-onboard-primary prep-save-btn"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving…" : isDrawer ? "Save Changes" : "Save & Enter Negotiation →"}
          </button>
        </footer>
      </div>
    </div>
  );
}
