import re
from pathlib import Path

import pytest
import yaml

from nlab.knowledge import get_knowledge_base

CONTENT = Path(__file__).resolve().parents[3] / "content"

# Book pages of each tool in the CCHN Field Manual (2019), widened by a few pages for the module introductions
FIELD_MANUAL_TOOLS = {
    1: (46, 63),
    2: (64, 84),
    3: (85, 105),
    4: (106, 136),
    5: (137, 151),
    6: (152, 167),
    7: (168, 177),
    8: (178, 188),
    9: (193, 217),
    10: (218, 229),
    11: (230, 249),
    12: (250, 276),
    13: (277, 288),
    14: (288, 310),
    15: (313, 331),
    16: (332, 339),
    17: (340, 375),
}
DIALS = {"trust", "rigidity", "hostility", "consistency"}
# Phrasing the manual tells negotiators to avoid (FM p. 185, p. 240): no "Try" line may recommend it
AVOIDED = [
    "i understand your",
    "i understand this situation",
    "non-negotiable",
    "we will never accept",
    "i apologize",
    "i'm sorry",
]


def moves() -> set[str]:
    rules = yaml.safe_load((CONTENT / "behaviour_rules.yaml").read_text(encoding="utf-8"))
    return set(rules["moves"])


def test_every_cchn_tool_has_exactly_one_note_with_a_citation_inside_the_tool() -> None:
    kb = get_knowledge_base()
    for number, (first, last) in FIELD_MANUAL_TOOLS.items():
        doc = kb.get(f"cchn-tool-{number:02d}")
        assert doc is not None, f"no note for Tool {number}"
        assert doc.framework.startswith("CCHN")
        assert f"Tool {number}," in doc.citation, doc.citation
        pages = re.search(r"Field Manual \(2019\), Tool \d+, pp?\. (\d+)(?:-(\d+))?", doc.citation)
        assert pages, doc.citation
        start, end = int(pages.group(1)), int(pages.group(2) or pages.group(1))
        assert first <= start <= end <= last, f"Tool {number}: pp. {start}-{end} is outside pp. {first}-{last}"


def test_notes_map_only_to_moves_and_dials_that_exist() -> None:
    known = moves()
    for doc in get_knowledge_base().all_docs():
        assert set(doc.mapped_moves) <= known, (doc.id, set(doc.mapped_moves) - known)
        assert set(doc.mapped_dials) <= DIALS, (doc.id, set(doc.mapped_dials) - DIALS)
        assert doc.summary and doc.citation and doc.body_markdown


def test_practice_notes_name_their_own_source_and_are_not_called_cchn() -> None:
    practice = [doc for doc in get_knowledge_base().all_docs() if doc.id.startswith("practice-")]
    assert len(practice) >= 5
    for doc in practice:
        assert not doc.framework.startswith("CCHN"), doc.id
        assert "CCHN" not in doc.title, doc.id
        assert "How this relates to CCHN" in doc.body_markdown, doc.id


@pytest.mark.parametrize("doc", get_knowledge_base().all_docs(), ids=lambda doc: doc.id)
def test_no_note_recommends_phrasing_the_manual_warns_against(doc) -> None:  # type: ignore[no-untyped-def]
    for line in doc.body_markdown.splitlines():
        if re.match(r"\s*[*-]\s*\*Try", line):
            assert not any(phrase in line.lower() for phrase in AVOIDED), (doc.id, line)


def test_relevance_search_finds_the_matching_tool() -> None:
    kb = get_knowledge_base()
    hostile = [
        doc.id for doc in kb.find_relevant(query="Why did the guard shout and get hostile?", dials=["hostility"])
    ]
    assert "cchn-tool-08" in hostile
    iceberg = [
        doc.id
        for doc in kb.find_relevant(query="What were his motives behind the position?", moves=["identifies_interest"])
    ]
    assert "cchn-tool-09" in iceberg
    lines = [doc.id for doc in kb.find_relevant(query="Where should my bottom line and red line be?")]
    assert {"cchn-tool-13", "cchn-tool-17"} & set(lines)
