from nlab.llm.answers import ClassifierAnswer, Evaluation
from nlab.llm.quotes import clean_classification, clean_scores

MOVES = {"asks_good_question", "threatens"}


def test_the_classifier_loses_unsupported_evidence():
    raw = ClassifierAnswer.model_validate(
        {
            "moves": [
                {"id": "asks_good_question", "quote": "What worries you?"},
                {"id": "threatens", "quote": "I will call your boss"},
                {"id": "not_a_move", "quote": "What worries you?"},
            ],
            "red_lines": [{"text": "No payment", "quote": "cash", "action": "accepts"}],
            "proposals": [
                {"issue": "route", "side": "counterpart", "line": "bottom_line", "quote": "What worries you?"}
            ],
            "operational_details": [{"id": "route", "quote": "imagined route"}],
        }
    )
    cleaned, dropped = clean_classification(raw, "What worries you?", MOVES)
    assert [(m.id, m.quote) for m in cleaned.moves] == [("asks_good_question", "What worries you?")]
    assert cleaned.red_lines == [] and len(cleaned.proposals) == 1 and cleaned.operational_details == []
    assert dropped == 4


def test_only_offering_or_accepting_a_red_line_counts():
    said = "we prefer No armed escort, and the people are a driver and me"
    line = "No armed escort by a party to the conflict"
    raw = ClassifierAnswer.model_validate(
        {
            "red_lines": [
                {"text": line, "quote": "we prefer No armed escort", "action": "declines"},
                {"text": line, "quote": "a driver and me", "action": "mentions"},
            ],
            "mandate_breaches": [{"text": "Changing the route", "quote": "a driver", "action": "mentions"}],
        }
    )
    cleaned, _ = clean_classification(raw, said, MOVES)
    assert cleaned.red_lines == [] and cleaned.mandate_breaches == []  # defending the line is not crossing it
    raw = ClassifierAnswer.model_validate(
        {"red_lines": [{"text": line, "quote": "we prefer No armed escort", "action": "accepts"}]}
    )
    cleaned, _ = clean_classification(raw, said, MOVES)
    assert [item.text for item in cleaned.red_lines] == [line]


def test_scores_require_a_trainee_quote():
    raw = Evaluation.model_validate(
        {
            "scores": [
                {"id": "questioning", "score": 4, "quote": "What worries you?"},
                {"id": "trust_building", "score": 5, "quote": "imagined quote"},
                {"id": "not_in_the_rubric", "score": 5, "quote": "What worries you?"},
            ]
        }
    )
    cleaned, dropped = clean_scores(raw, ["What worries you?"], ["questioning", "trust_building"])
    assert [(s.id, s.score) for s in cleaned.scores] == [("questioning", 4), ("trust_building", None)]
    assert dropped == 2  # the unknown dimension and the unquoted score are both dropped


def test_null_quotes_are_no_evidence():
    raw = Evaluation.model_validate(
        {
            "scores": [
                {"id": "questioning", "score": None, "quote": None},
                {"id": "trust_building", "score": 4, "quote": "What worries you?"},
            ]
        }
    )
    cleaned, _ = clean_scores(raw, ["What worries you?"], ["questioning", "trust_building"])
    assert cleaned.scores[0].model_dump() == {"id": "questioning", "score": None, "quote": ""}
    assert cleaned.scores[1].score == 4
    moves, _ = clean_classification(
        ClassifierAnswer.model_validate({"moves": [{"id": "asks_good_question", "quote": None}]}), "x", MOVES
    )
    assert moves.moves == []


def test_a_flag_needs_a_trainee_quote():
    raw = Evaluation.model_validate(
        {"flags": [{"text": "Rude", "quote": "idiot"}, {"text": "Vague", "quote": "maybe"}]}
    )
    cleaned, dropped = clean_scores(raw, ["You idiot."], [])
    assert [f.text for f in cleaned.flags] == ["Rude"] and dropped == 1


def test_the_debrief_keeps_only_notes_whose_quote_is_in_the_transcript():
    from nlab.llm.answers import Debrief
    from nlab.llm.quotes import clean_debrief
    from nlab.llm.types import Line

    lines = [
        Line(role="character", text="Visits need written authorisation.", turn=0),
        Line(role="trainee", text="Could we start with the medical unit?", turn=1),
        Line(role="character", text="Is there anything else I can assist you with?", turn=1),
        Line(role="trainee", text="What would protect you if you were asked later?", turn=2),
    ]
    raw = Debrief.model_validate(
        {
            "summary": "s",
            "strengths": [],
            "improvements": [],
            "did_well": [
                {"turn": 1, "note": "A concrete step.", "quote": "could we start with the medical unit?"},
                {"turn": 2, "note": "Invented.", "quote": "I promise full access"},
                {"turn": 1, "note": "Wrong turn named.", "quote": "What would protect you"},
                {"turn": 1, "note": "No quote.", "quote": ""},
            ],
            "missed": [
                {
                    "turn": 1,
                    "note": "He opened a door.",
                    "quote": "anything else I can assist",
                    "try_instead": "What is hardest?",
                },
                {"turn": 1, "note": "No alternative.", "quote": "anything else I can assist", "try_instead": " "},
                {"turn": 1, "note": "Not said.", "quote": "never said", "try_instead": "Ask."},
            ],
            "one_focus": {"title": " ", "advice": "x"},
        }
    )
    cleaned, dropped = clean_debrief(raw, lines)
    assert [(n.turn, n.note) for n in cleaned.did_well] == [(1, "A concrete step."), (2, "Wrong turn named.")]
    assert [(n.turn, n.try_instead) for n in cleaned.missed] == [(1, "What is hardest?")]
    assert cleaned.one_focus is None
    assert dropped == 2 + 2  # two did_well and two missed


def test_the_debrief_shows_at_most_three_of_each():
    from nlab.llm.answers import Debrief
    from nlab.llm.quotes import clean_debrief
    from nlab.llm.types import Line

    lines = [Line(role="trainee", text="hello there", turn=1)]
    note = {"turn": 1, "note": "n", "quote": "hello"}
    raw = Debrief.model_validate(
        {"summary": "s", "strengths": [], "improvements": [], "did_well": [note] * 5, "missed": []}
    )
    cleaned, dropped = clean_debrief(raw, lines)
    assert len(cleaned.did_well) == 3 and dropped == 2
