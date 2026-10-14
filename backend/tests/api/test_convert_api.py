import copy
import shutil

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from nlab.api.content import load_content
from nlab.api.settings import Settings
from nlab.db.models import LlmCall, Scenario
from nlab.llm import LLMConfig, RoleConfig
from nlab.llm.convert import example_output, split_bank
from tests.api.support import count, draft, org_with_admin, sign_in
from tests.conftest import CONTENT
from tests.llm.fakes import FakeProvider

pytestmark = pytest.mark.anyio

CONFIG = LLMConfig(default=RoleConfig(model="deepseek-flash", api_key=SecretStr("k")))
BRIEF = next(
    chunk for chunk in split_bank((CONTENT / "scenario_bank.md").read_text(encoding="utf-8")) if chunk["n"] == 1
)["text"]


def reply_with_extra_actor(kind):
    scenario = draft()
    if kind == "counterpart":
        second = copy.deepcopy(scenario["counterparts"][0])
        second.update(id="second", hidden_interests=[], challenges=[])
        second.pop("opening", None)
        scenario["counterparts"].append(second)
    elif kind == "stakeholder":
        scenario["stakeholders"] = [{"id": "liaison", "role": "Militia liaison"}]
    else:
        scenario["multiparty"] = {}
    return example_output(scenario)


@pytest.mark.parametrize("setting", [None, "false", "true"])
@pytest.mark.parametrize("kind", ["counterpart", "stakeholder", "multiparty"])
async def test_generation_obeys_the_multiple_counterparts_environment_setting(
    app, new_client, monkeypatch, setting, kind
):
    if setting is None:
        monkeypatch.delenv("NLAB_ALLOW_MULTIPLE_COUNTERPARTS", raising=False)
    else:
        monkeypatch.setenv("NLAB_ALLOW_MULTIPLE_COUNTERPARTS", setting)
    app.state.settings = Settings(
        _env_file=None, **app.state.settings.model_dump(exclude={"allow_multiple_counterparts"})
    )
    provider = FakeProvider([reply_with_extra_actor(kind)] * 3)
    app.state.llm = (provider, CONFIG)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    response = await alice.post("/api/scenarios/convert", json={"text": "# Camp access\n\n" + BRIEF})
    assert response.status_code == 200, response.text
    body = response.json()
    if setting == "true":
        assert body["errors"] == [] and body["scenario"] is not None
    else:
        assert body["scenario"] is None  # the builder cannot save an invalid multi-actor draft
        assert any("exactly one counterpart" in error for error in body["errors"])
    assert await count(app, Scenario) == 0


async def test_generation_retries_an_extra_actor_and_accepts_one_counterpart(app, new_client):
    provider = FakeProvider([reply_with_extra_actor("counterpart"), example_output(draft())])
    app.state.llm = (provider, CONFIG)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    response = await alice.post("/api/scenarios/convert", json={"text": "# Camp access\n\n" + BRIEF})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["errors"] == [] and len(body["scenario"]["counterparts"]) == 1
    assert "exactly one counterpart" in provider.requests[1].messages[-1]["content"]
    assert await count(app, LlmCall) == 2


async def test_a_brief_becomes_a_checked_draft_that_is_not_saved(app, new_client, tmp_path):
    for filename in ("behaviour_rules.yaml", "rubric.yaml"):
        shutil.copy(CONTENT / filename, tmp_path / filename)
    shutil.copytree(CONTENT / "scenarios", tmp_path / "scenarios")
    content = app.state.content = load_content(tmp_path)  # generation needs no scenario bank document
    gold = next(scenario for scenario in content.curated if scenario["id"] == "s01_idp_camp_access")
    checkpoint = next(scenario for scenario in content.curated if scenario["id"] == "s09_hostile_checkpoint")
    provider = FakeProvider([example_output(gold)])
    app.state.llm = (provider, CONFIG)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    converted = await alice.post(
        "/api/scenarios/convert", json={"text": "# Camp access\n\n" + BRIEF, "filename": "brief.md"}
    )
    assert converted.status_code == 200, converted.text
    body = converted.json()
    assert body["errors"] == [] and body["scenario"]["id"] == "camp_access"
    assert body["scenario"]["review"]["status"] == "draft"
    prompt = provider.requests[0].messages[1]["content"]
    assert prompt.count("## Example scenario:") == 2
    assert f"## Example scenario: {gold['title']}" in prompt
    assert f"## Example scenario: {checkpoint['title']}" in prompt
    assert prompt.split("# Convert this brief\n", 1)[1].endswith("# Camp access\n\n" + BRIEF + "\n")
    assert await count(app, Scenario) == 0  # nothing saved
    assert await count(app, LlmCall) == 1  # one call, on the ledger
    me = (await alice.get("/api/me")).json()
    async with app.state.sessionmaker() as db:
        call = (await db.execute(select(LlmCall.user_id, LlmCall.org_id))).one()
    assert str(call.user_id) == me["id"] and str(call.org_id) == me["active_org"]["id"]


async def test_without_a_model_conversion_is_unavailable(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/scenarios/convert", json={"text": "A brief."})).status_code == 503


async def test_a_brief_must_hold_one_scenario(app, new_client):
    app.state.llm = (FakeProvider([]), CONFIG)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/scenarios/convert", json={"text": "   "})).status_code == 422
    two = "# SCENARIO 01 — A\nx\n# SCENARIO 02 — B\ny"
    refused = await alice.post("/api/scenarios/convert", json={"text": two})
    assert refused.status_code == 422 and "one at a time" in refused.json()["detail"]


class ExplodingProvider(FakeProvider):
    """Answers the first call, then fails like a network error."""

    async def complete(self, config, request, schema=None, json=False):
        if self.answers:
            return await super().complete(config, request, schema, json)
        self.requests.append(request)
        raise ConnectionError("provider unreachable")


async def test_a_failing_model_call_answers_502_and_stays_on_the_ledger(app, new_client):
    """First attempt answers malformed JSON; the retry raises (provider error). Both attempts stay on the ledger."""
    app.state.llm = (ExplodingProvider(["not json"]), CONFIG)  # second complete() raises, like a provider error
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    response = await alice.post("/api/scenarios/convert", json={"text": "# A\n\nSome brief text."})
    assert response.status_code == 502 and response.json()["detail"] == "The language model did not answer"
    assert await count(app, LlmCall) == 2
    async with app.state.sessionmaker() as db:
        rows = sorted((await db.execute(select(LlmCall.outcome, LlmCall.role))).all())
    assert rows == [("error", "converter"), ("malformed", "converter")]


async def test_the_converters_taken_ids_are_only_the_visible_slugs(app, new_client):
    """A slug that exists only in another org must not force a _2 suffix: that would reveal it exists."""
    admin_b, _ = await org_with_admin(new_client, "Org B")
    taken = draft(scenario_id="camp_access")
    assert (await admin_b.post("/api/scenarios", json={"content": taken})).status_code == 201
    content = app.state.content
    gold = next(scenario for scenario in content.curated if scenario["id"] == "s01_idp_camp_access")
    app.state.llm = (FakeProvider([example_output(gold)]), CONFIG)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    converted = await alice.post("/api/scenarios/convert", json={"text": "# Camp access\n\n" + BRIEF})
    assert converted.status_code == 200, converted.text
    assert converted.json()["scenario"]["id"] == "camp_access"
