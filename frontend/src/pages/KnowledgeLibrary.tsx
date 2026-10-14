import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router";
import type { S } from "../api/client";
import { KnowledgeModal } from "../features/coach/KnowledgeModal";
import { useLoad } from "../hooks";
import { Problem } from "../ui";
import { IconX } from "../icons";

export function KnowledgeLibrary() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const docs = useLoad<S["KnowledgeDocOut"][]>("knowledge");

  const [search, setSearch] = useState("");
  const [hiddenFrameworks, setHiddenFrameworks] = useState<Set<string>>(new Set()); // unchecked in the dropdown: all selected by default
  const [fwOpen, setFwOpen] = useState(false);
  const fwRef = useRef<HTMLDivElement>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [activeDocId, setActiveDocId] = useState<string | null>(id ?? null);

  // Extract unique frameworks and top tags
  const frameworks = useMemo(() => {
    if (!docs.data) return [];
    const set = new Set<string>();
    for (const d of docs.data) {
      if (d.framework) set.add(d.framework);
    }
    return Array.from(set).sort();
  }, [docs.data]);

  const allTags = useMemo(() => {
    if (!docs.data) return [];
    const count: Record<string, number> = {};
    for (const d of docs.data) {
      for (const t of d.tags || []) {
        count[t] = (count[t] || 0) + 1;
      }
    }
    return Object.entries(count)
      .sort((a, b) => b[1] - a[1])
      .map(([tag]) => tag);
  }, [docs.data]);

  const filteredDocs = useMemo(() => {
    if (!docs.data) return [];
    return docs.data.filter((doc) => {
      if (doc.framework && hiddenFrameworks.has(doc.framework)) {
        return false;
      }
      if (selectedTag && !doc.tags?.includes(selectedTag)) {
        return false;
      }
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesTitle = doc.title.toLowerCase().includes(q);
        const matchesSummary = doc.summary.toLowerCase().includes(q);
        const matchesCitation = doc.citation?.toLowerCase().includes(q);
        const matchesTags = doc.tags?.some((t) => t.toLowerCase().includes(q));
        if (!matchesTitle && !matchesSummary && !matchesCitation && !matchesTags) {
          return false;
        }
      }
      return true;
    });
  }, [docs.data, hiddenFrameworks, selectedTag, search]);

  useEffect(() => {
    if (!fwOpen) return;
    const close = (e: MouseEvent) => {
      if (!fwRef.current?.contains(e.target as Node)) setFwOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [fwOpen]);

  const toggleFramework = (fw: string) => {
    setHiddenFrameworks((current) => {
      const next = new Set(current);
      if (next.has(fw)) next.delete(fw);
      else next.add(fw);
      return next;
    });
  };

  const handleOpenDoc = (docId: string) => {
    setActiveDocId(docId);
  };

  const handleCloseDoc = () => {
    setActiveDocId(null);
    if (id) {
      navigate("/knowledge");
    }
  };

  return (
    <div className="knowledge-library-page">
      <div className="session-heading">
        <div>
          <div className="eyebrow">Frontline Doctrine & Research</div>
          <h1>Knowledge Library</h1>
          <p className="lead-text">
            Explore doctrinal guidance from the Centre of Competence on Humanitarian Negotiation (CCHN) Field Manual,
            along with tactical practice notes on conflict styles, BATNA, and de-escalation.
          </p>
        </div>
      </div>

      <Problem text={docs.error} />

      {/* Filter and Search Controls */}
      <div className="knowledge-controls">
        <div className="knowledge-search-bar">
          <input
            type="search"
            placeholder="Search doctrine by topic, tool name, or keyword..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search doctrine knowledge"
          />
          <div className="framework-dropdown" ref={fwRef}>
            <button
              type="button"
              className="filter-btn framework-dropdown-toggle"
              aria-expanded={fwOpen}
              aria-haspopup="true"
              onClick={() => setFwOpen((open) => !open)}
            >
              Frameworks{hiddenFrameworks.size > 0 ? ` (${frameworks.length - hiddenFrameworks.size}/${frameworks.length})` : ""} ▾
            </button>
            {fwOpen && (
              <div className="framework-dropdown-menu" role="group" aria-label="Filter by framework">
                {frameworks.map((fw) => {
                  const count = docs.data?.filter((d) => d.framework === fw).length ?? 0;
                  return (
                    <label key={fw} className="framework-option">
                      <input
                        type="checkbox"
                        checked={!hiddenFrameworks.has(fw)}
                        onChange={() => toggleFramework(fw)}
                      />
                      <span>{fw}</span>
                      <span className="framework-option-count">{count}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="knowledge-filter-row">
          {selectedTag && (
            <div className="active-tag-indicator">
              <span>Filtered by tag: <strong>#{selectedTag}</strong></span>
              <button type="button" className="tag-clear-btn" onClick={() => setSelectedTag(null)} aria-label="Clear tag filter">
                <IconX size={12} />
              </button>
            </div>
          )}
        </div>

        {/* Popular Tags */}
        {allTags.length > 0 && (
          <div className="knowledge-tags-bar" aria-label="Doctrine tags">
            <span className="tags-label">Topics:</span>
            <div className="tags-list">
              {allTags.slice(0, 12).map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className={`tag-pill ${selectedTag === tag ? "active" : ""}`}
                  onClick={() => setSelectedTag(selectedTag === tag ? null : tag)}
                >
                  #{tag}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Document Grid */}
      {docs.data && (
        <div className="knowledge-grid">
          {filteredDocs.length === 0 ? (
            <div className="empty-knowledge-state">
              <p>No doctrine articles match your search or filter.</p>
              <button
                type="button"
                className="button secondary small"
                onClick={() => {
                  setSearch("");
                  setHiddenFrameworks(new Set());
                  setSelectedTag(null);
                }}
              >
                Clear all filters
              </button>
            </div>
          ) : (
            filteredDocs.map((doc) => (
              <article
                key={doc.id}
                className="knowledge-card"
                onClick={() => handleOpenDoc(doc.id)}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleOpenDoc(doc.id);
                  }
                }}
                aria-label={`Open doctrine: ${doc.title}`}
              >
                <div className="knowledge-card-top">
                  <span className={`framework-pill ${doc.framework?.includes("CCHN") ? "cchn" : "practice"}`}>
                    {doc.framework?.includes("CCHN") ? "CCHN" : "Practice"}
                  </span>
                </div>

                <h3>{doc.title}</h3>
                <p className="card-summary">{doc.summary}</p>

                <div className="knowledge-card-footer">
                  <div className="card-tags">
                    {(doc.tags || []).slice(0, 3).map((tag) => (
                      <span key={tag} className="tag-mini">
                        #{tag}
                      </span>
                    ))}
                  </div>
                  <span className="read-more-link">Read Doctrine →</span>
                </div>
              </article>
            ))
          )}
        </div>
      )}

      {/* Modal reader when a document is opened */}
      {activeDocId && (
        <KnowledgeModal docId={activeDocId} onClose={handleCloseDoc} />
      )}
    </div>
  );
}
