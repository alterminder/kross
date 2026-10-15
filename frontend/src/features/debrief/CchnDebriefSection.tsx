import { useState, type FormEvent } from "react";
import { api, type S } from "../../api/client";
import { KnowledgeModal } from "../coach/KnowledgeModal";
import {
  IconAlertTriangle,
  IconAward,
  IconBook,
  IconBookOpen,
  IconCheck,
  IconClipboard,
  IconFileText,
  IconLayers,
  IconPencil,
  IconScale,
  IconTag,
  IconTarget,
  IconX,
} from "../../icons";

export interface CchnDebriefSectionProps {
  sessionId: string;
  cchnDebrief?: S["CchnDebriefOut"] | null;
  initialReflection?: Record<string, string> | null;
  onReflectionSaved?: (answers: Record<string, string>) => void;
}

type ActiveTab = "agreement" | "dynamics" | "prep_reality" | "reflection" | "competences";

export function CchnDebriefSection({
  sessionId,
  cchnDebrief,
  initialReflection,
  onReflectionSaved,
}: CchnDebriefSectionProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>("agreement");
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  const reflectionData = cchnDebrief?.reflection;
  const initialAnswers: Record<string, string> = {};
  if (reflectionData?.questions) {
    for (const q of reflectionData.questions) {
      initialAnswers[q.id] = (initialReflection && initialReflection[q.id]) || q.answer || "";
    }
  } else if (initialReflection) {
    Object.assign(initialAnswers, initialReflection);
  }

  const [reflectionAnswers, setReflectionAnswers] = useState<Record<string, string>>(initialAnswers);
  const [savingReflection, setSavingReflection] = useState(false);
  const [reflectionSavedMessage, setReflectionSavedMessage] = useState<string | null>(null);
  const [reflectionError, setReflectionError] = useState<string | null>(null);

  if (!cchnDebrief) return null;

  const {
    agreement_check,
    zones,
    level_timeline,
    iceberg_depth,
    deescalation_report,
    prep_vs_reality,
    reflection,
    competences,
    knowledge_links,
  } = cchnDebrief;

  const handleSaveReflection = async (e: FormEvent) => {
    e.preventDefault();
    setSavingReflection(true);
    setReflectionError(null);
    setReflectionSavedMessage(null);

    try {
      await api<void>(`sessions/${sessionId}/reflection`, {
        method: "PUT",
        body: { answers: reflectionAnswers },
      });
      setReflectionSavedMessage("Reflection saved and synced with your AI Coach!");
      if (onReflectionSaved) {
        onReflectionSaved(reflectionAnswers);
      }
    } catch (err) {
      setReflectionError((err as Error).message || "Failed to save reflection");
    } finally {
      setSavingReflection(false);
    }
  };

  const getZoneBadgeClass = (zone: string) => {
    switch (zone) {
      case "F":
        return "zone-pill zone-f";
      case "D":
        return "zone-pill zone-d";
      case "E":
      case "RED":
        return "zone-pill zone-e";
      default:
        return "zone-pill zone-neutral";
    }
  };

  const getLevelPillClass = (level: string) => {
    switch (level.toLowerCase()) {
      case "technical":
        return "level-pill level-technical";
      case "professional":
        return "level-pill level-professional";
      case "political":
        return "level-pill level-political";
      default:
        return "level-pill";
    }
  };

  const getAlignmentBadgeClass = (alignment: string) => {
    switch (alignment) {
      case "aligned":
        return "step-chip";
      case "diverged":
        return "anti-chip";
      default:
        return "clean-chip";
    }
  };

  const hasAgreement = Boolean(agreement_check || zones);
  const hasDynamics = Boolean(level_timeline || iceberg_depth || deescalation_report);
  const hasPrepReality = Boolean(prep_vs_reality);
  const hasReflection = Boolean(reflection);
  const hasCompetences = Boolean(competences);

  const availableTabs: ActiveTab[] = [];
  if (hasAgreement) availableTabs.push("agreement");
  if (hasDynamics) availableTabs.push("dynamics");
  if (hasPrepReality) availableTabs.push("prep_reality");
  if (hasReflection) availableTabs.push("reflection");
  if (hasCompetences) availableTabs.push("competences");

  if (availableTabs.length === 0) return null;

  const currentTab = availableTabs.includes(activeTab) ? activeTab : availableTabs[0];

  return (
    <section className="cchn-debrief-section" aria-label="CCHN Doctrine Debrief & Reflection">
      <div className="cchn-header-bar">
        <div>
          <div className="cchn-badge">
            <span><IconBook size={14} /> CCHN Field Doctrine Analysis</span>
          </div>
          <h2>CCHN Strategic Reflection</h2>
          <p className="cchn-subtitle">
            Evaluation based on the CCHN Field Manual: Agreement Quality, Negotiation Zones, Dialogue Levels, and Tactical Dynamics.
          </p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <nav className="cchn-tabs" aria-label="Debrief Navigation">
        {hasAgreement && (
          <button
            type="button"
            className={`cchn-tab-btn ${currentTab === "agreement" ? "active" : ""}`}
            onClick={() => setActiveTab("agreement")}
          >
            <IconClipboard size={14} /> Agreement & Zones
          </button>
        )}
        {hasDynamics && (
          <button
            type="button"
            className={`cchn-tab-btn ${currentTab === "dynamics" ? "active" : ""}`}
            onClick={() => setActiveTab("dynamics")}
          >
            <IconLayers size={14} /> Levels, Iceberg & Hostility
          </button>
        )}
        {hasPrepReality && (
          <button
            type="button"
            className={`cchn-tab-btn ${currentTab === "prep_reality" ? "active" : ""}`}
            onClick={() => setActiveTab("prep_reality")}
          >
            <IconTarget size={14} /> Prep vs Reality
          </button>
        )}
        {hasReflection && (
          <button
            type="button"
            className={`cchn-tab-btn ${currentTab === "reflection" ? "active" : ""}`}
            onClick={() => setActiveTab("reflection")}
          >
            <IconPencil size={14} /> Self-Reflection (T6)
          </button>
        )}
        {hasCompetences && (
          <button
            type="button"
            className={`cchn-tab-btn ${currentTab === "competences" ? "active" : ""}`}
            onClick={() => setActiveTab("competences")}
          >
            <IconAward size={14} /> Competences & Doctrine
          </button>
        )}
      </nav>

      {/* Tab 1: Agreement & Zones */}
      {currentTab === "agreement" && (
        <div className="cchn-tab-content">
          <div className="cchn-card-grid">
            {/* Agreement Check Card */}
            {agreement_check && (
              <div className="card cchn-card">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">Tool 7 · Agreement Quality Check</span>
                    <h3>Drafted Terms & 5 CCHN Criteria</h3>
                  </div>
                  <button
                    type="button"
                    className="cchn-tool-link-btn"
                    onClick={() => setSelectedDocId(agreement_check.doc_id || "cchn-tool-07")}
                  >
                    <IconBookOpen size={14} /> Doctrine Tool 7
                  </button>
                </div>

                <div className="agreement-summary-banner">
                  <div className="agreement-status">
                    <span className={`status-tag ${agreement_check.is_deal ? "deal" : "no-deal"}`}>
                      {agreement_check.is_deal ? (
                        <>
                          <IconCheck size={14} /> Agreement Concluded
                        </>
                      ) : (
                        <>
                          <IconX size={14} /> No Formal Agreement
                        </>
                      )}
                    </span>
                    <div className="agreement-score-display">
                      Score: <strong>{agreement_check.overall_score}</strong> / 100
                    </div>
                  </div>
                </div>

                {/* Terms Sheet */}
                <div className="terms-sheet-box">
                  <h4>Agreed Terms Sheet</h4>
                  {agreement_check.terms_sheet && agreement_check.terms_sheet.length > 0 ? (
                    <ul className="terms-list">
                      {agreement_check.terms_sheet.map((term, idx) => (
                        <li key={idx} className="term-item">
                          <span className="term-bullet">§</span>
                          <span>{term}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted terms-empty">No clear terms recorded in this session transcript.</p>
                  )}
                </div>

                {/* 5 CCHN Criteria */}
                <div className="criteria-list">
                  <h4>CCHN 5 Essential Criteria for Agreements</h4>
                  <div className="criteria-grid">
                    {(agreement_check.criteria ?? []).map((crit) => (
                      <div key={crit.id} className="criterion-card">
                        <div className="criterion-top">
                          <span className="criterion-label">{crit.label}</span>
                          <span className={`criterion-score score-${crit.score}`}>
                            {crit.status === "met" ? "Met (2/2)" : crit.status === "partial" ? "Partial (1/2)" : "Unmet (0/2)"}
                          </span>
                        </div>
                        <p className="criterion-finding">{crit.finding}</p>
                        {crit.evidence && <blockquote className="criterion-evidence">“{crit.evidence}”</blockquote>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Negotiation Zones Card */}
            {zones && (
              <div className="card cchn-card">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">Tools 13 & 14 · Negotiation Zones</span>
                    <h3>Zone Determination & Issue Parking</h3>
                  </div>
                  <button
                    type="button"
                    className="cchn-tool-link-btn"
                    onClick={() => setSelectedDocId(zones.doc_id || "cchn-tool-13")}
                  >
                    <IconBookOpen size={14} /> Doctrine Tool 13 & 14
                  </button>
                </div>

              <div className="zone-indicator-row">
                <span className={getZoneBadgeClass(zones.zone)}>
                  Zone {zones.zone}: {zones.zone_label}
                </span>
                <p className="zone-desc">{zones.description}</p>
              </div>

              {/* A-B-C Scale Visualization */}
              <div className="scale-visualization-box">
                <h4>A–B–C Negotiation Lines (Tool 13)</h4>
                <div className="scale-parties-grid">
                  {zones.scale?.trainee && (
                    <div className="scale-party-card">
                      <h5>Your Lines (Humanitarian)</h5>
                      <ul className="scale-lines-list">
                        <li>
                          <span className="line-tag line-a">Line A (Ideal)</span>
                          <p>{zones.scale.trainee.ideal_outcome || "Full unconditional access"}</p>
                        </li>
                        <li>
                          <span className="line-tag line-b">Line B (Bottom)</span>
                          <p>{zones.scale.trainee.bottom_line || "Neutral oversight with verification"}</p>
                        </li>
                        <li>
                          <span className="line-tag line-c">Line C (Red)</span>
                          <p>{zones.scale.trainee.red_line || "Armed escort or compromised integrity"}</p>
                        </li>
                      </ul>
                    </div>
                  )}

                  {zones.scale?.counterpart && (
                    <div className="scale-party-card">
                      <h5>Counterpart Lines</h5>
                      <ul className="scale-lines-list">
                        <li>
                          <span className="line-tag line-a">Line A (Ideal)</span>
                          <p>{zones.scale.counterpart.ideal_outcome || "Direct control and inspection"}</p>
                        </li>
                        <li>
                          <span className="line-tag line-b">Line B (Bottom)</span>
                          <p>{zones.scale.counterpart.bottom_line || "Prior manifest and verification"}</p>
                        </li>
                        <li>
                          <span className="line-tag line-c">Line C (Red)</span>
                          <p>{zones.scale.counterpart.red_line || "Unvetted free transit"}</p>
                        </li>
                      </ul>
                    </div>
                  )}
                </div>
              </div>

              {/* Tier 3 Parking */}
              <div className="tier-parking-box">
                <div className="tier-header">
                  <h4>Tier-3 Issue Parking (Tool 14)</h4>
                  <span className={`parking-badge ${zones.tier_3_parked ? "parked-ok" : "parked-breached"}`}>
                    {zones.tier_3_parked ? (
                      <>
                        <IconCheck size={14} /> Non-Negotiables Parked
                      </>
                    ) : (
                      <>
                        <IconAlertTriangle size={14} /> Tier-3 Breach / Unparked
                      </>
                    )}
                  </span>
                </div>
                <p className="muted">
                  Under CCHN methodology, Tier-3 existential/mandate topics must be parked outside transactional bartering to protect operational integrity.
                </p>

                {(zones.tier_3_issues ?? []).length > 0 && (
                  <ul className="tier-issues-list">
                    {zones.tier_3_issues?.map((issue) => (
                      <li key={issue.id} className={`tier-issue-item ${issue.status === "conceded" ? "breached" : "parked"}`}>
                        <div className="tier-issue-title">
                          <strong>{issue.label}</strong>
                          <span className="tier-status-text">
                            {issue.status === "conceded" ? "Conceded / Breached" : issue.status === "parked" ? "Parked" : issue.status}
                          </span>
                        </div>
                        {issue.finding && <p className="tier-notes">{issue.finding}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Dynamics, Levels & Hostility */}
      {currentTab === "dynamics" && (
        <div className="cchn-tab-content">
          <div className="cchn-card-grid">
            {/* Level Timeline Card */}
            {level_timeline && (
              <div className="card cchn-card">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">Tool 4 · Dialogue Levels</span>
                    <h3>Conversation Level Movements</h3>
                  </div>
                  <button
                    type="button"
                    className="cchn-tool-link-btn"
                    onClick={() => setSelectedDocId(level_timeline.doc_id || "cchn-tool-04")}
                  >
                    <IconBookOpen size={14} /> Doctrine Tool 4
                  </button>
                </div>

                <div className="level-summary-bar">
                  <div className="level-progression">
                    <span>Start: <strong className={getLevelPillClass(level_timeline.start_level)}>{level_timeline.start_level}</strong></span>
                    <span className="arrow">→</span>
                    <span>Final: <strong className={getLevelPillClass(level_timeline.final_level)}>{level_timeline.final_level}</strong></span>
                  </div>
                  <p className="level-summary-text">{level_timeline.summary}</p>
                </div>

                {/* Turn-by-Turn Level Timeline */}
                <div className="level-entries-container">
                  <h4>Turn-by-Turn Level Progression</h4>
                  <div className="level-timeline-list">
                    {(level_timeline.entries ?? []).map((entry, idx) => (
                      <div key={idx} className={`level-entry-row speaker-${entry.speaker}`}>
                        <div className="entry-meta">
                          <span className="turn-tag">Turn {entry.turn}</span>
                          <span className="speaker-tag">{entry.speaker === "trainee" ? "You" : "Counterpart"}</span>
                          <span className={getLevelPillClass(entry.level)}>{entry.level}</span>
                          {entry.direction && (
                            <span className={`direction-tag dir-${entry.direction}`}>
                              {entry.direction === "politicize" ? "↗ Politicized" : "↘ Depoliticized"}
                            </span>
                          )}
                          {!entry.matched && (
                            <span className="direction-tag dir-politicize">Level Mismatch</span>
                          )}
                        </div>
                        <p className="entry-analysis">{entry.note}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Iceberg Depth Card */}
            {iceberg_depth && (
              <div className="card cchn-card">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">Tool 9 · Counterpart Iceberg</span>
                    <h3>3-Layer Iceberg Depth Reached</h3>
                  </div>
                  <button
                    type="button"
                    className="cchn-tool-link-btn"
                    onClick={() => setSelectedDocId(iceberg_depth.doc_id || "cchn-tool-09")}
                  >
                    <IconBookOpen size={14} /> Doctrine Tool 9
                  </button>
                </div>

                <div className="iceberg-status-banner">
                  <span>Maximum Layer Uncovered:</span>
                  <span className="iceberg-max-pill">
                    {iceberg_depth.max_layer_reached === "motives_values"
                      ? "Layer 3: Motives & Deep Values"
                      : iceberg_depth.max_layer_reached === "reasoning"
                      ? "Layer 2: Tactical Reasoning"
                      : iceberg_depth.max_layer_reached === "position"
                      ? "Layer 1: Stated Position"
                      : "Surface Only"}
                  </span>
                  <p className="muted">{iceberg_depth.summary}</p>
                </div>

                {/* Visual 3-Layer Iceberg */}
                <div className="iceberg-visual-stack">
                  {(iceberg_depth.layers ?? []).map((layer) => (
                    <div
                      key={layer.layer}
                      className={`iceberg-layer-box layer-${layer.layer} ${layer.reached ? "reached" : "unreached"}`}
                    >
                      <div className="iceberg-layer-header">
                        <div className="layer-title-group">
                          <span className="layer-icon">{layer.reached ? "✓" : "○"}</span>
                          <h5>{layer.label}</h5>
                        </div>
                        <span className={`layer-badge ${layer.reached ? "badge-reached" : "badge-missed"}`}>
                          {layer.reached ? "Reached" : "Not Reached"}
                        </span>
                      </div>

                      <div className="layer-body">
                        <div className="layer-row">
                          <span className="layer-field-label">Revealed in negotiation:</span>
                          <div className="layer-content">
                            {layer.counterpart_content && layer.counterpart_content.length > 0 ? (
                              <ul className="terms-list">
                                {layer.counterpart_content.map((item, cIdx) => (
                                  <li key={cIdx}>• {item}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="muted">Nothing revealed at this depth.</p>
                            )}
                          </div>
                        </div>
                        {layer.prep_guess && (
                          <div className="layer-row prep-row">
                            <span className="layer-field-label">Your prep hypothesis:</span>
                            <p className="layer-content">“{layer.prep_guess}”</p>
                          </div>
                        )}
                        {layer.accuracy_note && (
                          <p className="layer-accuracy muted">
                            <em>Analysis:</em> {layer.accuracy_note}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* De-escalation & Hostility Report Card */}
            {deescalation_report && (
              <div className="card cchn-card full-width">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">Tool 8 · De-escalation Protocol</span>
                    <h3>Hostility Management & 6-Step Protocol</h3>
                  </div>
                  <button
                    type="button"
                    className="cchn-tool-link-btn"
                    onClick={() => setSelectedDocId(deescalation_report.doc_id || "cchn-tool-08")}
                  >
                    <IconBookOpen size={14} /> Doctrine Tool 8
                  </button>
                </div>

              <p className="deescalation-summary-text">{deescalation_report.summary}</p>

              {(deescalation_report.incidents ?? []).length > 0 ? (
                <div className="incidents-table-wrapper">
                  <table className="incidents-table">
                    <thead>
                      <tr>
                        <th>Turn</th>
                        <th>Trigger / Hostility</th>
                        <th>Your Response</th>
                        <th>6-Step Protocol Observed</th>
                        <th>Anti-Patterns</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deescalation_report.incidents?.map((inc, idx) => (
                        <tr key={idx}>
                          <td>
                            <span className="turn-tag">{inc.turn}</span>
                          </td>
                          <td>
                            <div className="hostility-meter">
                              <span className="hostility-dots">
                                {/* the dial runs 0–100; the meter is 5 dots, one per 20 */}
                                {"●".repeat(Math.min(5, Math.max(0, Math.round(inc.hostility_level / 20))))}
                                {"○".repeat(Math.max(0, 5 - Math.min(5, Math.max(0, Math.round(inc.hostility_level / 20)))))}
                              </span>
                              <span className="hostility-num">{inc.hostility_level}/100</span>
                            </div>
                            <p className="incident-trigger">{inc.trigger}</p>
                            <span className="muted">Outcome: {inc.outcome}</span>
                          </td>
                          <td>
                            <blockquote className="incident-response">“{inc.trainee_quote}”</blockquote>
                          </td>
                          <td>
                            <div className="steps-chips">
                              {inc.steps_observed && inc.steps_observed.length > 0 ? (
                                inc.steps_observed.map((step, sIdx) => (
                                  <span key={sIdx} className="step-chip">
                                    <IconCheck size={12} /> {step}
                                  </span>
                                ))
                              ) : (
                                <span className="muted">None observed</span>
                              )}
                            </div>
                          </td>
                          <td>
                            <div className="antipattern-chips">
                              {inc.anti_patterns_observed && inc.anti_patterns_observed.length > 0 ? (
                                inc.anti_patterns_observed.map((anti, aIdx) => (
                                  <span key={aIdx} className="anti-chip">
                                    <IconAlertTriangle size={14} /> {anti}
                                  </span>
                                ))
                              ) : (
                                <span className="clean-chip">None detected</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted">No severe hostility spikes detected in this negotiation.</p>
              )}
            </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Prep vs Reality */}
      {currentTab === "prep_reality" && prep_vs_reality && (
        <div className="cchn-tab-content">
          <div className="card cchn-card">
            <div className="cchn-card-header">
              <div>
                <span className="eyebrow">Naivasha Grid · Preparation vs Encounter</span>
                <h3>Hypotheses vs Operational Reality</h3>
              </div>
              <button
                type="button"
                className="cchn-tool-link-btn"
                onClick={() => setSelectedDocId(prep_vs_reality.doc_id || "cchn-naivasha-grid")}
              >
                <IconBookOpen size={14} /> Naivasha Grid Doctrine
              </button>
            </div>

            <div className="prep-reality-summary-banner">
              <p>{prep_vs_reality.summary}</p>
            </div>

            {prep_vs_reality.has_preparation ? (
              <div className="prep-reality-modules-grid">
                {(prep_vs_reality.modules ?? []).map((m) => (
                  <div key={m.module_id} className="prep-module-card">
                    <div className="prep-module-header">
                      <h4>{m.label}</h4>
                      <div className="alignment-badge">
                        <span className={getAlignmentBadgeClass(m.alignment)}>
                          {m.alignment.toUpperCase()}
                        </span>
                      </div>
                    </div>

                    <div className="prep-vs-reality-columns">
                      <div className="prep-col">
                        <span className="col-label">Pre-Negotiation Sheet</span>
                        <p>{m.planned || "Not planned in sheet."}</p>
                      </div>
                      <div className="reality-col">
                        <span className="col-label">Observed Live Encounter</span>
                        <p>{m.reality}</p>
                      </div>
                    </div>

                    <div className="prep-takeaway-box">
                      <span className="takeaway-label">Key Doctrine Takeaway:</span>
                      <p>{m.insight}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="prep-empty-state">
                <span className="empty-icon"><IconFileText size={20} /></span>
                <h4>No Preparation Sheet Submitted</h4>
                <p>
                  You skipped or left empty the pre-negotiation Naivasha Grid before starting this scenario.
                  Completing preparation allows the debrief engine to benchmark your tactical predictions against counterpart responses.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Reflection (Tool 6) */}
      {currentTab === "reflection" && reflection && (
        <div className="cchn-tab-content">
          <div className="card cchn-card">
            <div className="cchn-card-header">
              <div>
                <span className="eyebrow">Tool 6 · Post-Negotiation Review</span>
                <h3>Transaction Reflection Checklist</h3>
              </div>
              <button
                type="button"
                className="cchn-tool-link-btn"
                onClick={() => setSelectedDocId(reflection.doc_id || "cchn-tool-06")}
              >
                <IconBookOpen size={14} /> Doctrine Tool 6
              </button>
            </div>

            <p className="cchn-reflection-intro">
              Capturing your immediate tactical reflections solidifies practitioner experience.
              Your answers are also directly integrated into your interactive AI Coach debrief session below.
            </p>

            {reflectionSavedMessage && (
              <div className="cchn-toast-success" role="status">
                <IconCheck size={14} /> {reflectionSavedMessage}
              </div>
            )}
            {reflectionError && (
              <div className="cchn-toast-error" role="alert">
                <IconX size={14} /> {reflectionError}
              </div>
            )}

            <form onSubmit={handleSaveReflection} className="cchn-reflection-form">
              {(reflection.questions ?? []).map((q) => (
                <div key={q.id} className="reflection-question-block">
                  <div className="question-header">
                    <span className="category-tag">{q.guidance}</span>
                    <label htmlFor={`field-${q.id}`}>
                      <strong>{q.prompt}</strong>
                    </label>
                  </div>

                  {q.id === "fh_conflict_style" && (
                    <div className="style-selector-row">
                      <div className="style-chips-group">
                        {[
                          { style: "Competing", desc: "High assertiveness, low cooperativeness" },
                          { style: "Collaborating", desc: "High assertiveness, high cooperativeness" },
                          { style: "Compromising", desc: "Moderate assertiveness, moderate cooperativeness" },
                          { style: "Avoiding", desc: "Low assertiveness, low cooperativeness" },
                          { style: "Accommodating", desc: "Low assertiveness, high cooperativeness" },
                        ].map((item) => (
                          <button
                            key={item.style}
                            type="button"
                            className="style-chip-btn"
                            title={item.desc}
                            onClick={() => {
                              const curr = reflectionAnswers[q.id] || "";
                              if (!curr.includes(item.style)) {
                                const next = curr ? `${item.style}: ${curr}` : `${item.style} - `;
                                setReflectionAnswers((prev) => ({ ...prev, [q.id]: next }));
                              }
                            }}
                          >
                            <IconTag size={13} /> {item.style}
                          </button>
                        ))}
                      </div>
                      <button
                        type="button"
                        className="cchn-tool-link-btn mini"
                        onClick={() => setSelectedDocId("practice-conflict-styles")}
                      >
                        <IconBookOpen size={14} /> FH Session 12 Note
                      </button>
                    </div>
                  )}

                  {q.id === "fh_challenge_or_dilemma" && (
                    <div className="style-selector-row">
                      <div className="style-chips-group">
                        {[
                          { label: "Operational Challenge", desc: "Solvable with tactics & resources" },
                          { label: "Humanitarian Dilemma", desc: "Tension between fundamental principles / mandate" },
                        ].map((item) => (
                          <button
                            key={item.label}
                            type="button"
                            className="style-chip-btn"
                            title={item.desc}
                            onClick={() => {
                              const curr = reflectionAnswers[q.id] || "";
                              if (!curr.includes(item.label)) {
                                const next = curr ? `${item.label}: ${curr}` : `${item.label} - `;
                                setReflectionAnswers((prev) => ({ ...prev, [q.id]: next }));
                              }
                            }}
                          >
                            <IconScale size={13} /> {item.label}
                          </button>
                        ))}
                      </div>
                      <button
                        type="button"
                        className="cchn-tool-link-btn mini"
                        onClick={() => setSelectedDocId("cchn-challenges-dilemmas")}
                      >
                        <IconBookOpen size={14} /> FH Session 1 Note
                      </button>
                    </div>
                  )}

                  <textarea
                    id={`field-${q.id}`}
                    rows={4}
                    value={reflectionAnswers[q.id] ?? ""}
                    placeholder="Reflect on your tactical moves, feelings, or unexpected counterpart reactions..."
                    onChange={(e) =>
                      setReflectionAnswers((prev) => ({
                        ...prev,
                        [q.id]: e.target.value,
                      }))
                    }
                  />
                </div>
              ))}

              <div className="reflection-form-actions">
                <button
                  type="submit"
                  className="button primary reflection-save-btn"
                  disabled={savingReflection}
                >
                  {savingReflection ? "Saving Reflection…" : "Save Reflection & Sync with Coach"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tab 5: Competences & Doctrine Links */}
      {currentTab === "competences" && (
        <div className="cchn-tab-content">
          <div className="cchn-card-grid">
            {/* Competences Card */}
            {competences && (
              <div className="card cchn-card">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">CCHN Competence Matrix</span>
                    <h3>Core, Advanced & Expert Progression</h3>
                  </div>
                  <button
                    type="button"
                    className="cchn-tool-link-btn"
                    onClick={() => setSelectedDocId(competences.doc_id || "cchn-competences")}
                  >
                    <IconBookOpen size={14} /> Competence Framework
                  </button>
                </div>

              <div className="competence-tiers-list">
                {(competences.tiers ?? []).map((tier) => (
                  <div key={tier.tier} className={`competence-tier-card tier-${tier.tier}`}>
                    <div className="tier-header-row">
                      <div>
                        <span className="tier-level-badge">{tier.tier.toUpperCase()} TIER</span>
                        <h4>{tier.label}</h4>
                      </div>
                    </div>

                    <p className="tier-summary">{tier.summary}</p>

                    <div className="tier-skills-wrapper">
                      <span className="skills-subheading">Dimensions Evaluated:</span>
                      <div className="skills-tags">
                        {(tier.dimensions ?? []).map((dim) => (
                          <span key={dim.id} className="skill-chip">
                            {dim.label} {dim.score !== null && dim.score !== undefined ? `(${dim.score}/5)` : ""}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            )}

            {/* Knowledge Links Card */}
            {(knowledge_links ?? []).length > 0 && (
              <div className="card cchn-card">
                <div className="cchn-card-header">
                  <div>
                    <span className="eyebrow">Doctrinal Knowledge Library</span>
                    <h3>CCHN Field Reference Notes</h3>
                  </div>
                </div>

                <p className="muted">
                  Each finding in this debrief links directly to the normative field tools defined by the Centre of Competence on Humanitarian Negotiation:
                </p>

                <div className="knowledge-links-grid">
                  {(knowledge_links ?? []).map((link) => (
                    <div key={link.id} className="knowledge-link-card">
                      <div className="link-card-top">
                        <span className="link-framework-pill">{link.framework}</span>
                        <h5>{link.title}</h5>
                        <span className="link-citation muted">{link.citation}</span>
                      </div>
                      <p className="link-summary">{link.summary}</p>
                      <div className="link-card-bottom">
                        <div className="link-tags">
                          {(link.tags ?? []).map((tag, tIdx) => (
                            <span key={tIdx} className="link-tag">
                              #{tag}
                            </span>
                          ))}
                        </div>
                        <button
                          type="button"
                          className="cchn-read-note-btn"
                          onClick={() => setSelectedDocId(link.id)}
                        >
                          Read Doctrine Note →
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Doctrine Knowledge Inspection Modal */}
      {selectedDocId && (
        <KnowledgeModal
          docId={selectedDocId}
          onClose={() => setSelectedDocId(null)}
        />
      )}
    </section>
  );
}
