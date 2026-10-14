"""transcript(): the conversation as the LLM layer reads it — pure, no database needed."""

import uuid

from nlab.db.models import Turn
from nlab.db.sessions import transcript


def turn(number: int, trainee: str | None, reply: str | None, active: str | None) -> Turn:
    return Turn(
        session_id=uuid.uuid4(),
        number=number,
        trainee_text=trainee,
        reply_text=reply,
        classification={},
        engine_state_after={"active_interlocutor": active} if active else {},
        events=[],
    )


def test_transcript_tags_both_sides_with_the_turns_party():
    lines = transcript(
        [
            turn(0, None, "State your business.", "gov_colonel"),
            turn(1, "One truck, Colonel.", "No.", "gov_colonel"),
            turn(2, "Commander, two trucks?", "Maybe.", "opposition_cmdr"),
        ]
    )
    by_text = {line.text: line.speaker for line in lines}
    assert by_text["One truck, Colonel."] == "gov_colonel"  # the trainee line carries the party too
    assert by_text["No."] == "gov_colonel"
    assert by_text["Commander, two trucks?"] == "opposition_cmdr"
    assert by_text["State your business."] == "gov_colonel"


def test_transcript_leaves_single_party_lines_untagged():
    lines = transcript([turn(1, "Hello?", "Yes?", None)])
    assert all(line.speaker is None for line in lines)
