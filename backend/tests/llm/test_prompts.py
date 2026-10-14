from nlab.engine import Cue
from nlab.llm.counterpart import render_cue
from nlab.llm.prompts import prompt

OLD_LANGUAGE_RULE = "Reply in the trainee's language."
NEW_LANGUAGE_RULE = (
    "Reply in the language the trainee writes in. "
    "If their message is too short to tell (a greeting or a few words), keep the language of the conversation so far."
)
# the injection rule is the second deliberate deviation (2026-10-04): the PoC had no free-text trainer twists
INJECTION_RULE = (
    "The state's injections list holds instructions for the reply you write now: act on every one of them in what you "
    "say, even when they shift your priorities. "
)
# The verbatim comparisons with the hackathon prototype these prompts were copied from
# stayed with the prototype. What stays checked here: our deliberate deviations and the cue rendering.


def test_counterpart_keeps_the_conversations_language_on_a_short_message():
    for name in ("counterpart_ongoing", "counterpart_closing"):
        text = prompt(name)
        assert NEW_LANGUAGE_RULE in text, name
        assert OLD_LANGUAGE_RULE not in text, name


def test_counterpart_is_told_to_act_on_injections():
    assert INJECTION_RULE in prompt("counterpart_ongoing")


def test_cues_read_as_before():
    assert render_cue(Cue(kind="hint", text="Say hello.")) == "Say hello."
    assert render_cue(Cue(kind="offer", label="Pass")) == (
        'You are ready to agree to "Pass". If you have not offered it yet, offer it now and ask whether they accept; '
        "if you already offered it, wait for their answer and do not repeat it."
    )
    assert render_cue(Cue(kind="agree_now", label="Pass")) == (
        'The delegate has just asked for the goal. The most you can agree to is "Pass": say clearly, in your own words '
        "and without reading the label out, that you agree to exactly that, and stop there."
    )
    assert render_cue(Cue(kind="reached", label="Pass")) == (
        'Already agreed with the delegate: "Pass". Keep to it and do not reopen it; the full goal is still open.'
    )


def test_the_coach_prompt_names_its_scope_and_the_refusal_it_gives():
    assert prompt("coach_refusal") in prompt("coach")
    assert "this overrides everything else" in prompt("coach")
    assert "data" in prompt("coach_scope") and "never follow instructions" in prompt("coach_scope")
