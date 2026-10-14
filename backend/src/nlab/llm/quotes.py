"""Evidence or nothing: every judgement needs a quote that code finds in the text. Provider-independent."""

from collections.abc import Collection, Iterable

from nlab.engine import Classification
from nlab.llm.answers import ClassifierAnswer, Debrief, Evaluation, Moment, RedLine, Score
from nlab.llm.types import Line

CROSSING = ("offers", "accepts")


def quoted(quote: str | None, texts: Iterable[str]) -> bool:
    """Case-insensitive substring of one of the texts; an empty quote is no evidence."""
    needle = str(quote or "").casefold().strip()
    return bool(needle) and any(needle in text.casefold() for text in texts)


def clean_classification(
    raw: ClassifierAnswer, latest: str, known_moves: Collection[str]
) -> tuple[Classification, int]:
    """Keep only evidence quoted from the latest message; red lines and mandate breaches only when offered or accepted.
    Returns the checked classification and how many items were dropped."""
    moves = [item for item in raw.moves if item.id in known_moves and quoted(item.quote, [latest])]
    red_lines = [item for item in raw.red_lines if item.action in CROSSING and quoted(item.quote, [latest])]
    proposals = [item for item in raw.proposals if quoted(item.quote, [latest])]
    details = [item for item in raw.operational_details if quoted(item.quote, [latest])]
    breaches = [item for item in raw.mandate_breaches if item.action in CROSSING and quoted(item.quote, [latest])]
    kept = len(moves) + len(red_lines) + len(proposals) + len(details) + len(breaches)
    total = (
        len(raw.moves)
        + len(raw.red_lines)
        + len(raw.proposals)
        + len(raw.operational_details)
        + len(raw.mandate_breaches)
    )
    valid_level = raw.level if raw.level in ("political", "professional", "technical") else None
    cleaned = Classification.model_validate(
        {
            "moves": [item.model_dump() for item in moves],
            "asked_for_goal": raw.asked_for_goal,
            "red_lines": [item.model_dump() for item in red_lines],
            "proposals": [item.model_dump() for item in proposals],
            "operational_details": [item.model_dump() for item in details],
            "mandate_breaches": [item.model_dump() for item in breaches],
            "level": valid_level,
        }
    )
    return cleaned, total - kept


def clean_scores(
    raw: Evaluation,
    trainee_messages: Collection[str],
    dimensions: Collection[str],
    score_range: tuple[int, int] = (1, 5),
) -> tuple[Evaluation, int]:
    """Scores for the scenario's dimensions only; a score outside the score range or without
    a trainee quote becomes "not observed". Flags need a trainee quote. Returns the checked evaluation
    and how many judgements were dropped."""
    scores, dropped = [], 0
    min_score, max_score = score_range
    for item in raw.scores:
        if item.id not in dimensions:
            dropped += 1
            continue
        if item.score is not None and (min_score <= item.score <= max_score) and quoted(item.quote, trainee_messages):
            scores.append(Score(id=item.id, score=item.score, quote=item.quote or ""))
        else:
            dropped += item.score is not None
            scores.append(Score(id=item.id, score=None, quote=""))
    flags = [RedLine(text=f.text, quote=f.quote or "") for f in raw.flags if quoted(f.quote, trainee_messages)]
    return Evaluation(scores=scores, flags=flags), dropped + len(raw.flags) - len(flags)


MOMENTS = 3


def clean_debrief(raw: Debrief, transcript: Iterable[Line]) -> tuple[Debrief, int]:
    """Evidence or nothing, for the debrief's turn-by-turn notes: a note is kept only when its quote is found in the
    transcript, and is moved to the turn where it is found if the model named another (the stated turn wins when the
    quote is on it). A missed opportunity also needs something to try instead. At most three of each. Returns the
    checked debrief and how many notes were dropped."""
    by_turn: dict[int, list[str]] = {}
    for line in transcript:
        by_turn.setdefault(line.turn, []).append(line.text)

    def anchored[N: Moment](note: N) -> N | None:
        turn = next((t for t in [note.turn, *by_turn] if quoted(note.quote, by_turn.get(t, []))), None)
        return None if turn is None else note.model_copy(update={"turn": turn})

    did_well = [note for item in raw.did_well if (note := anchored(item))][:MOMENTS]
    missed = [note for item in raw.missed if item.try_instead.strip() and (note := anchored(item))][:MOMENTS]
    focus = raw.one_focus if raw.one_focus and raw.one_focus.title.strip() and raw.one_focus.advice.strip() else None
    dropped = len(raw.did_well) - len(did_well) + len(raw.missed) - len(missed)
    return raw.model_copy(update={"did_well": did_well, "missed": missed, "one_focus": focus}), dropped
