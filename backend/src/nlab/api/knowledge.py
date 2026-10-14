from fastapi import APIRouter

from nlab.api.deps import OrgDep
from nlab.api.schemas import KnowledgeDocOut
from nlab.db.errors import NotFound
from nlab.knowledge import get_knowledge_base

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge(context: OrgDep) -> list[KnowledgeDocOut]:
    """Returns all doctrine documents from the CCHN and frontline negotiation knowledge base."""
    kb = get_knowledge_base()
    return [
        KnowledgeDocOut(
            id=d.id,
            title=d.title,
            framework=d.framework,
            citation=d.citation,
            tags=d.tags,
            summary=d.summary,
            body_markdown=d.body_markdown,
        )
        for d in kb.all_docs()
    ]


@router.get("/{doc_id}")
async def read_knowledge(doc_id: str, context: OrgDep) -> KnowledgeDocOut:
    """Returns one specific doctrine document by ID."""
    kb = get_knowledge_base()
    doc = kb.get(doc_id)
    if not doc:
        raise NotFound(f"Doctrine document '{doc_id}' not found")
    return KnowledgeDocOut(
        id=doc.id,
        title=doc.title,
        framework=doc.framework,
        citation=doc.citation,
        tags=doc.tags,
        summary=doc.summary,
        body_markdown=doc.body_markdown,
    )
