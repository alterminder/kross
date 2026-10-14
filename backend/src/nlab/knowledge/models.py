from pydantic import BaseModel, Field


class KnowledgeDoc(BaseModel):
    """One frontline negotiation doctrine document from the CCHN or ICRC knowledge base."""

    id: str
    title: str
    framework: str
    citation: str
    tags: list[str] = Field(default_factory=list)
    mapped_moves: list[str] = Field(default_factory=list)
    mapped_dials: list[str] = Field(default_factory=list)
    summary: str
    body_markdown: str
    raw_markdown: str = ""

    def short_citation(self) -> str:
        return f"{self.title} ({self.citation})"
