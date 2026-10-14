from nlab.llm.agreement import UNCERTAIN_GAP, compare_scores
from nlab.llm.answers import Evaluation


def evaluation(**scores: int | None) -> Evaluation:
    return Evaluation.model_validate(
        {"scores": [{"id": key, "score": value, "quote": "x" if value else ""} for key, value in scores.items()]}
    )


def test_a_gap_of_two_or_more_is_uncertain():
    assert UNCERTAIN_GAP == 2
    rows = {row.id: row for row in compare_scores(evaluation(a=4, b=4, c=5, d=2), evaluation(a=3, b=2, c=1, d=4))}
    assert [rows[k].uncertain for k in "abcd"] == [False, True, True, True]
    assert (rows["b"].first, rows["b"].second) == (4, 2)


def test_scored_by_one_pass_only_is_uncertain_and_by_neither_is_not_listed():
    rows = compare_scores(evaluation(a=3, b=None, c=None), evaluation(a=None, b=2))
    assert [(row.id, row.first, row.second, row.uncertain) for row in rows] == [
        ("a", 3, None, True),
        ("b", None, 2, True),
    ]


def test_the_first_pass_is_the_one_shown():
    rows = compare_scores(evaluation(a=3), evaluation(a=3, extra=1))
    assert [row.id for row in rows] == ["a"] and not rows[0].uncertain
