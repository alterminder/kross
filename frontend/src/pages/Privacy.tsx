import { useMemo } from "react";
import { Link } from "react-router";
import { marked } from "marked";
import notice from "./privacy.md?raw";

export function Privacy() {
  // privacy.md is our own static file, so the rendered HTML needs no sanitiser
  const html = useMemo(() => marked.parse(notice, { async: false }) as string, []);
  return (
    <main className="privacy">
      <p>
        <Link to="/">← KROSS</Link>
      </p>
      <div className="knowledge-content-text" dangerouslySetInnerHTML={{ __html: html }} />
    </main>
  );
}
