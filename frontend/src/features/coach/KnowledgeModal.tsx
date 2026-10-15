import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import { api, type S } from "../../api/client";
import { Problem } from "../../ui";
import { IconBook, IconX } from "../../icons";

interface KnowledgeModalProps {
  docId: string;
  onClose: () => void;
}

export function KnowledgeModal({ docId, onClose }: KnowledgeModalProps) {
  const [doc, setDoc] = useState<S["KnowledgeDocOut"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const renderedContent = useMemo(() => {
    if (!doc?.body_markdown) return "";
    // Strip leading H1 heading if present, since doc.title is already in the modal header
    let cleaned = doc.body_markdown.replace(/^\s*#\s+[^\n]*\n+/, "");
    // "How KROSS uses it" is internal engine material (see content/knowledge/README.md): keep it out of the reader
    cleaned = cleaned.replace(/\n##\s+How KROSS uses it[^]*?(?=\n## )/i, "");
    cleaned = cleaned.replace(/\n##\s+How KROSS uses it[^]*$/i, "");
    return marked.parse(cleaned, { async: false }) as string;
  }, [doc?.body_markdown]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api<S["KnowledgeDocOut"]>(`knowledge/${docId}`)
      .then((data) => {
        if (alive) {
          setDoc(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (alive) {
          setError((err as Error).message);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [docId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="knowledge-modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="knowledge-modal" onClick={(e) => e.stopPropagation()}>
        <div className="knowledge-modal-header">
          <div>
            <span className="knowledge-framework-pill"><IconBook size={14} /> CCHN Doctrine Framework</span>
            <h2>{doc?.title ?? "Loading Doctrine..."}</h2>
            {doc?.citation && <p className="knowledge-citation">{doc.citation}</p>}
          </div>
          <button type="button" className="close-button" onClick={onClose} aria-label="Close doctrine modal">
            <IconX size={16} />
          </button>
        </div>

        <div className="knowledge-modal-body">
          {error && <Problem text={error} />}
          {loading && <p className="loading">Loading doctrine tool…</p>}
          {doc && (
            <>
              <div className="knowledge-summary-box">
                <h4>Core Doctrinal Principle</h4>
                <p>{doc.summary}</p>
              </div>

              {doc.tags.length > 0 && (
                <div className="knowledge-tags">
                  {doc.tags.map((t) => (
                    <span key={t} className="knowledge-tag">
                      #{t}
                    </span>
                  ))}
                </div>
              )}

              <div
                className="knowledge-content-text"
                dangerouslySetInnerHTML={{ __html: renderedContent }}
              />
            </>
          )}
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
