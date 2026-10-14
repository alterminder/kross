"""Do two independent scoring passes of the same transcript agree? A dimension whose scores differ by two points or
more, or that one pass scored and the other did not observe, is uncertain: the trainee is told so instead of being
shown a figure as if it were firm. Pure code, no model call."""

from pydantic import BaseModel

from nlab.llm.answers import Evaluation

UNCERTAIN_GAP = 2  # on the 1-5 scale


class ScoreCheck(BaseModel):
    id: str
    first: int | None
    second: int | None
    uncertain: bool


def compare_scores(first: Evaluation, second: Evaluation) -> list[ScoreCheck]:
    """One row per dimension the first pass scored (in its order). A dimension the second pass left out counts as not
    observed there. Dimensions only the second pass mentions are ignored: the first pass is the one shown."""
    other = {item.id: item.score for item in second.scores}
    rows = []
    for item in first.scores:
        a, b = item.score, other.get(item.id)
        if a is None and b is None:
            continue  # neither pass observed it: nothing to be unsure about
        uncertain = a is None or b is None or abs(a - b) >= UNCERTAIN_GAP
        rows.append(ScoreCheck(id=item.id, first=a, second=b, uncertain=uncertain))
    return rows
