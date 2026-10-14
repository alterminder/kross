import asyncio
import copy
import json
import re

import pytest
from pydantic import SecretStr

from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.convert import (
    TBA,
    convert_brief,
    convert_upload,
    example_output,
    facts,
    split_bank,
)
from tests.conftest import CONTENT, read_yaml
from tests.llm.fakes import FakeProvider

CONFIG = LLMConfig(default=RoleConfig(model="deepseek-flash", api_key=SecretStr("k")))
BANK = (CONTENT / "scenario_bank.md").read_text(encoding="utf-8")
GOLD = read_yaml(CONTENT / "scenarios" / "s01_idp_camp_access.yaml")
CHUNK = next(chunk for chunk in split_bank(BANK) if chunk["n"] == 1)


def test_a_verified_draft_and_a_rejected_paraphrase(rules, rubric):
    ok = asyncio.run(convert_brief(FakeProvider([example_output(GOLD)]), CONFIG, CHUNK, rules, rubric, []))
    assert not ok.errors, ok.errors
    draft = ok.scenario
    assert draft is not None and draft["review"]["status"] == "draft"
    assert "outcomes" in draft["review"]["needs_icrc_confirmation"]
    assert draft["counterparts"][0]["cultural_profile"] == TBA
    assert draft["generated"]["model"] == "deepseek-flash" and len(ok.records) == 1

    paraphrase = copy.deepcopy(GOLD)
    paraphrase["counterparts"][0]["opening"] = "We are very worried about your convoy."
    bad = asyncio.run(
        convert_brief(FakeProvider([example_output(paraphrase)]), CONFIG, CHUNK, rules, rubric, [], retries=0)
    )
    assert any("not copied verbatim" in error for error in bad.errors)


def test_text_around_the_json_does_not_cost_a_retry(rules, rubric):
    reply = "Here is the draft.\n```json\n" + example_output(GOLD) + "\n```\nEvery quote is verbatim. {done}"
    result = asyncio.run(convert_brief(FakeProvider([reply]), CONFIG, CHUNK, rules, rubric, [], retries=0))
    assert not result.errors and result.attempts == 1


def test_the_model_gets_the_errors_back_and_a_second_try(rules, rubric):
    paraphrase = copy.deepcopy(GOLD)
    paraphrase["counterparts"][0]["opening"] = "We are very worried about your convoy."
    provider = FakeProvider([example_output(paraphrase), example_output(GOLD)])
    result = asyncio.run(convert_brief(provider, CONFIG, CHUNK, rules, rubric, []))
    assert not result.errors and result.attempts == 2
    assert "not copied verbatim" in provider.requests[1].messages[-1]["content"]


@pytest.mark.parametrize("allow_multiple_counterparts", [False, True])
def test_one_counterpart_keeps_only_its_questions_from_a_two_speaker_brief(rules, rubric, allow_multiple_counterparts):
    chunk = next(chunk for chunk in split_bank(BANK) if chunk["n"] == 8)
    scenario = copy.deepcopy(GOLD)
    counterpart = scenario["counterparts"][0]
    counterpart.pop("opening")
    counterpart["challenges"] = re.findall(r'^\d+\. "(.+)"$', chunk["text"], re.M)[:5]  # Government's questions
    scenario["triggers"] = []
    scenario["rubric"]["indicators"] = []
    result = asyncio.run(
        convert_brief(
            FakeProvider([example_output(scenario)]),
            CONFIG,
            chunk,
            rules,
            rubric,
            [],
            retries=0,
            allow_multiple_counterparts=allow_multiple_counterparts,
        )
    )
    if allow_multiple_counterparts:
        assert result.errors == ["the brief has 10 numbered questions, the reply has 5 challenges"]
    else:
        assert not result.errors, result.errors
        assert result.scenario["counterparts"][0]["challenges"] == counterpart["challenges"]


def test_an_upload_gets_a_free_id_and_its_file_name(rules, rubric):
    text = "# Hospital roadblock\n\n" + CHUNK["text"]
    result = asyncio.run(
        convert_upload(
            FakeProvider([example_output(GOLD)]), CONFIG, text, "brief.md", {"hospital_roadblock"}, rules, rubric, []
        )
    )
    assert result.scenario is not None and result.scenario["id"] == "hospital_roadblock_2"
    assert result.scenario["sources"]["file"] == "brief.md" and "bank" not in result.scenario["sources"]


@pytest.mark.parametrize(
    ("text", "message"), [("  ", "empty"), ("# SCENARIO 01 — A\nx\n# SCENARIO 02 — B\ny", "one at a time")]
)
def test_an_upload_must_hold_one_brief(rules, rubric, text, message):
    with pytest.raises(ValueError, match=message):
        asyncio.run(convert_upload(FakeProvider([]), CONFIG, text, "", set(), rules, rubric, []))


def test_an_unknown_move_on_a_second_counterpart_is_rejected(rules, rubric):
    two = copy.deepcopy(GOLD)
    second = copy.deepcopy(two["counterparts"][0])
    second["id"] = "second"
    second["hidden_interests"] = [
        {"id": "secret", "layer": "motive_value", "text": "x", "reveal_when": {"move": "made_up_move"}}
    ]
    two["counterparts"].append(second)
    bad = asyncio.run(
        convert_brief(
            FakeProvider([example_output(two)]),
            CONFIG,
            CHUNK,
            rules,
            rubric,
            [],
            retries=0,
            allow_multiple_counterparts=True,
        )
    )
    assert "unknown move 'made_up_move'" in bad.errors


def test_failed_attempts_are_recorded_as_malformed(rules, rubric):
    bad = asyncio.run(convert_brief(FakeProvider(["not JSON"]), CONFIG, CHUNK, rules, rubric, [], retries=0))
    assert [record.outcome for record in bad.records] == ["malformed"]

    provider = FakeProvider(["not JSON", example_output(GOLD)])
    ok = asyncio.run(convert_brief(provider, CONFIG, CHUNK, rules, rubric, []))
    assert not ok.errors and [record.outcome for record in ok.records] == ["malformed", "ok"]


class ExplodingProvider(FakeProvider):
    """Answers the first call, then fails like a network error."""

    async def complete(self, config, request, schema=None, json=False):
        if self.answers:
            return await super().complete(config, request, schema, json)
        self.requests.append(request)
        raise ConnectionError("provider unreachable")


def test_a_provider_error_keeps_every_attempts_record(rules, rubric):
    from nlab.llm.convert import ConversionFailed

    provider = ExplodingProvider(["not json"])
    with pytest.raises(ConversionFailed) as failure:
        asyncio.run(convert_brief(provider, CONFIG, CHUNK, rules, rubric, []))
    assert [record.outcome for record in failure.value.records] == ["malformed", "error"]


VOCAB = [
    "Island of agreements",
    "Network Mapping",
    "Face-saving solutions",
    "Bottom Lines",
    "Normative Pathway",
    "Building trust and legitimacy",
]


def reply_with_skills(skills):
    """GOLD's verified reply with the model's own skill picks added."""
    body = json.loads(example_output(GOLD))
    body["skills"] = skills
    return json.dumps(body, ensure_ascii=False)


def without_skills_section(chunk):
    """The same brief, minus its Skills Tested section."""
    return {
        **chunk,
        "text": re.sub(r"^##\s*Skills Tested\s*$\n.*?(?=^#{1,3}\s|\Z)", "", chunk["text"], flags=re.M | re.S),
    }


def test_model_skills_are_kept_only_in_the_vocabulary(rules, rubric):
    ok = asyncio.run(
        convert_brief(
            FakeProvider(
                [
                    reply_with_skills(
                        [
                            "island of agreements",  # kept, in the vocabulary's spelling
                            "Invented Skill",  # dropped
                            "  Network Mapping ",  # kept despite the whitespace
                            "Face-saving solutions",
                            "Bottom Lines",
                            "Normative Pathway",
                            "Building trust and legitimacy",  # the sixth distinct valid one is dropped by the cap
                            "Island of agreements",  # the case-variant duplicate is deduped
                        ]
                    )
                ]
            ),
            CONFIG,
            without_skills_section(CHUNK),
            rules,
            rubric,
            [],
            VOCAB,
        )
    )
    assert not ok.errors, ok.errors
    draft = ok.scenario
    assert draft is not None and draft["skills_tested"] == [
        "Island of agreements",
        "Network Mapping",
        "Face-saving solutions",
        "Bottom Lines",
        "Normative Pathway",
    ]
    inferred = draft["review"]["needs_icrc_confirmation"]
    assert inferred.count("skills_tested") == 1  # the field path, once, never the labels
    assert "Invented Skill" not in inferred and "Invented Skill" not in draft["skills_tested"]


def test_too_few_skills_are_sent_back_for_repair(rules, rubric):
    provider = FakeProvider(
        [
            reply_with_skills([]),  # none at all
            reply_with_skills(["Island of agreements", "Network Mapping"]),  # still too few
            reply_with_skills(["Island of agreements", "Network Mapping", "Bottom Lines"]),  # repaired
        ]
    )
    ok = asyncio.run(convert_brief(provider, CONFIG, without_skills_section(CHUNK), rules, rubric, [], VOCAB))
    assert not ok.errors, ok.errors
    assert ok.attempts == 3
    for request in provider.requests[1:]:
        assert "choose 3 to 5 skills, exactly as written in the list" in request.messages[-1]["content"]


def test_on_the_last_attempt_too_few_skills_still_pass(rules, rubric):
    ok = asyncio.run(
        convert_brief(
            FakeProvider([reply_with_skills(["island of agreements", "Network Mapping"])]),
            CONFIG,
            without_skills_section(CHUNK),
            rules,
            rubric,
            [],
            VOCAB,
            retries=0,
        )
    )
    assert not ok.errors, ok.errors  # tags never sink a conversion
    draft = ok.scenario
    assert draft is not None and draft["skills_tested"] == ["Island of agreements", "Network Mapping"]
    assert "skills_tested" in draft["review"]["needs_icrc_confirmation"]


def test_a_skills_tested_section_stays_as_it_is(rules, rubric):
    ok = asyncio.run(
        convert_brief(
            FakeProvider([reply_with_skills(["Island of agreements", "Invented Skill"])]),
            CONFIG,
            CHUNK,
            rules,
            rubric,
            [],
            VOCAB,
        )
    )
    assert not ok.errors, ok.errors
    draft = ok.scenario
    assert draft is not None and draft["skills_tested"] == facts(CHUNK)["skills"]  # copied from the brief
    inferred = draft["review"]["needs_icrc_confirmation"]
    assert not any(skill in inferred for skill in VOCAB)  # the model's picks are ignored


def test_the_vocabulary_comes_from_the_curated_skills_only():
    from nlab.api.content import load_content

    vocabulary = load_content(CONTENT).skills_vocabulary
    assert "Island of agreements" in vocabulary  # a known curated skill, its vocabulary spelling
    assert "Network Mapping and Leveraging Influence Among Stakeholders" not in vocabulary  # no CCHN tool titles
