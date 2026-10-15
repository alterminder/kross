import logging
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from nlab.knowledge.models import KnowledgeDoc

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def default_knowledge_dir() -> Path:
    """Finds the content/knowledge directory across package, tests, and workspace layouts."""
    candidates = [
        Path(__file__).resolve().parents[4] / "content" / "knowledge",
        Path.cwd() / "content" / "knowledge",
        Path.cwd().parent / "content" / "knowledge",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


class KnowledgeBase:
    """In-memory index of frontline negotiation doctrine documents."""

    def __init__(self, docs: dict[str, KnowledgeDoc]) -> None:
        self.docs = docs

    def get(self, doc_id: str) -> KnowledgeDoc | None:
        return self.docs.get(doc_id)

    def all_docs(self) -> list[KnowledgeDoc]:
        return list(self.docs.values())

    def find_for_moves(self, moves: Iterable[str]) -> list[KnowledgeDoc]:
        """Finds knowledge docs mapped to any of the specified moves."""
        move_set = set(moves)
        results = [doc for doc in self.docs.values() if any(m in move_set for m in doc.mapped_moves)]
        return results

    def find_for_dials(self, dials: Iterable[str]) -> list[KnowledgeDoc]:
        """Finds knowledge docs mapped to any of the specified dials."""
        dial_set = set(dials)
        results = [doc for doc in self.docs.values() if any(d in dial_set for d in doc.mapped_dials)]
        return results

    def find_relevant(
        self,
        query: str = "",
        moves: Iterable[str] = (),
        dials: Iterable[str] = (),
        limit: int = 3,
    ) -> list[KnowledgeDoc]:
        """Ranks doctrine documents by query keyword match, move overlap, and dial overlap."""
        words = set(re.findall(r"\w+", query.lower())) if query else set()
        move_set = set(moves)
        dial_set = set(dials)

        scores: list[tuple[float, KnowledgeDoc]] = []
        for doc in self.docs.values():
            score = 0.0
            score += sum(3.0 for d in doc.mapped_dials if d in dial_set)
            score += sum(4.0 for m in doc.mapped_moves if m in move_set)
            if words:
                title_words = set(re.findall(r"\w+", doc.title.lower()))
                tag_words = {t.lower() for t in doc.tags}
                summary_words = set(re.findall(r"\w+", doc.summary.lower()))
                body_words = set(re.findall(r"\w+", doc.body_markdown.lower()))

                score += sum(3.0 for w in words if w in title_words)
                score += sum(2.5 for w in words if w in tag_words)
                score += sum(1.5 for w in words if w in summary_words)
                score += sum(0.5 for w in words if w in body_words)

            scores.append((score, doc))

        scores.sort(key=lambda item: (-item[0], item[1].id))
        return [doc for score, doc in scores[:limit]]


def parse_knowledge_doc(file_path: Path) -> KnowledgeDoc | None:
    """Parses a markdown file with YAML frontmatter into a KnowledgeDoc."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        logger.warning("Could not read knowledge file %s", file_path, exc_info=True)
        return None

    match = FRONTMATTER_RE.match(text)
    if not match:
        logger.warning("Knowledge file %s lacks YAML frontmatter", file_path)
        return None

    frontmatter_str, body = match.group(1), match.group(2)
    try:
        meta: dict[str, Any] = yaml.safe_load(frontmatter_str) or {}
    except Exception:
        logger.warning("Invalid YAML frontmatter in %s", file_path, exc_info=True)
        return None

    doc_id = str(meta.get("id") or file_path.stem)
    title = str(meta.get("title") or doc_id)
    framework = str(meta.get("framework") or "Frontline Humanitarian Negotiation")
    citation = str(meta.get("citation") or "")
    tags = [str(t) for t in meta.get("tags") or []]
    mapped_moves = [str(m) for m in meta.get("mapped_moves") or []]
    mapped_dials = [str(d) for d in meta.get("mapped_dials") or []]
    summary = str(meta.get("summary") or "")

    return KnowledgeDoc(
        id=doc_id,
        title=title,
        framework=framework,
        citation=citation,
        tags=tags,
        mapped_moves=mapped_moves,
        mapped_dials=mapped_dials,
        summary=summary,
        body_markdown=body.strip(),
        raw_markdown=text,
    )


def load_knowledge_base(directory: Path | None = None) -> KnowledgeBase:
    """Loads all knowledge markdown documents from the given directory (recursively)."""
    kb_dir = directory or default_knowledge_dir()
    docs: dict[str, KnowledgeDoc] = {}
    if kb_dir.is_dir():
        for file in sorted(kb_dir.rglob("*.md")):
            doc = parse_knowledge_doc(file)
            if doc:
                docs[doc.id] = doc

    logger.info("Loaded %d doctrine knowledge documents from %s", len(docs), kb_dir)
    return KnowledgeBase(docs)


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    """Cached singleton knowledge base instance."""
    return load_knowledge_base()
