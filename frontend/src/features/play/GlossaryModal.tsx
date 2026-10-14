import { useEffect } from "react";
import { IconBook, IconX } from "../../icons";

/** Frontline terminology and the four Naivasha Grid pillars, kept out of the play flow. */
export function GlossaryModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="knowledge-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Glossary">
      <div className="knowledge-modal glossary-modal" onClick={(e) => e.stopPropagation()}>
        <div className="knowledge-modal-header">
          <div>
            <span className="knowledge-framework-pill"><IconBook size={14} /> CCHN Doctrine Framework</span>
            <h2>Glossary</h2>
          </div>
          <button type="button" className="close-button" onClick={onClose} aria-label="Close glossary">
            <IconX size={16} />
          </button>
        </div>

        <div className="knowledge-modal-body">
          <div className="naivasha-preview-grid">
            <div className="naivasha-quadrant-card">
              <span className="quadrant-tag">QUADRANT 1</span>
              <h4>Internal Mandate</h4>
              <p>Establishing what you can decide locally vs what requires headquarters referral.</p>
            </div>
            <div className="naivasha-quadrant-card">
              <span className="quadrant-tag">QUADRANT 2</span>
              <h4>Counterpart Iceberg</h4>
              <p>Uncovering operational reasoning and deep values/fears beneath stated positions.</p>
            </div>
            <div className="naivasha-quadrant-card">
              <span className="quadrant-tag">QUADRANT 3</span>
              <h4>Island of Agreements</h4>
              <p>Grounding talks in agreed facts and convergent norms before tackling divergent issues.</p>
            </div>
            <div className="naivasha-quadrant-card">
              <span className="quadrant-tag">QUADRANT 4</span>
              <h4>Common Shared Space</h4>
              <p>The sustainable overlap where legitimate humanitarian action meets counterpart realities.</p>
            </div>
          </div>

          <div className="cchn-glossary-box">
            <span className="cchn-glossary-title">KEY FRONTLINE TERMINOLOGY</span>
            <div className="cchn-glossary-grid">
              <div className="glossary-item">
                <strong>Mandator:</strong>
                <span>The leadership body defining your mandate limits and red lines.</span>
              </div>
              <div className="glossary-item">
                <strong>Negotiator:</strong>
                <span>The frontline representative conducting direct face-to-face dialogue.</span>
              </div>
              <div className="glossary-item">
                <strong>Support Team:</strong>
                <span>HQ, legal, security, and technical specialists backing the negotiator.</span>
              </div>
              <div className="glossary-item">
                <strong>Bottom Line vs Red Line:</strong>
                <span>
                  A <em>red line</em> is an absolute ethical/legal limit; a <em>bottom line</em> is the minimum acceptable outcome before walking away.
                </span>
              </div>
              <div className="glossary-item">
                <strong>Iceberg:</strong>
                <span>The 3 levels of counterpart reality: visible Positions, Reasoning/Interests, and Values/Fears.</span>
              </div>
              <div className="glossary-item">
                <strong>Island of Agreements:</strong>
                <span>The initial baseline of shared facts and shared norms that anchors negotiation.</span>
              </div>
              <div className="glossary-item">
                <strong>Common Shared Space:</strong>
                <span>The zone of mutual operational feasibility where safe compromise is possible.</span>
              </div>
            </div>
          </div>
        </div>

        <div className="knowledge-modal-footer">
          <button type="button" className="btn-modal-close" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
