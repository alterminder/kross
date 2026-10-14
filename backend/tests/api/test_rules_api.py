import pytest

from nlab.db.models import RuleVersion
from tests.api.support import count, join, org_with_admin, sign_in

pytestmark = pytest.mark.anyio


def by_id(rules):
    return {move["id"]: move for move in rules["moves"]}


async def test_everyone_reads_the_rules_with_their_defaults(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    rules = (await alice.get("/api/rules")).json()
    assert set(rules["dials"]) == {"trust", "rigidity", "hostility", "consistency"}
    moves = by_id(rules)
    assert len(moves) == 73 and moves["evades_direct_question"]["deltas"] == {"trust": -3}
    assert not moves["evades_direct_question"]["changed"] and moves["insults_counterpart"]["ends_session"]
    assert rules["can_edit"]  # admin of her personal org


async def test_an_admin_edits_the_dial_changes_of_their_org_only(app, new_client):
    admin_a, _ = await org_with_admin(new_client, "Org A")
    admin_b, _ = await org_with_admin(new_client, "Org B")
    saved = await admin_a.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -6}}})
    assert saved.status_code == 200, saved.text
    edited = by_id(saved.json())["evades_direct_question"]
    assert edited["deltas"] == {"trust": -6} and edited["default"] == {"trust": -3} and edited["changed"]
    assert by_id((await admin_b.get("/api/rules")).json())["evades_direct_question"]["deltas"] == {"trust": -3}
    assert await count(app, RuleVersion) == 1


async def test_setting_the_default_again_clears_the_edit(app, new_client):
    admin, _ = await org_with_admin(new_client)
    await admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -6}}})
    back = await admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -3}}})
    assert not by_id(back.json())["evades_direct_question"]["changed"]


async def test_members_cannot_edit_rules(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    assert not (await bob.get("/api/rules")).json()["can_edit"]
    assert (await bob.put("/api/rules", json={"moves": {"threatens": {"trust": 1}}})).status_code == 403


async def test_a_bad_edit_names_the_problem(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    refused = await alice.put("/api/rules", json={"moves": {"no_such_move": {"trust": 1}}})
    assert refused.status_code == 422 and "Unknown move" in refused.json()["detail"]


async def test_sequential_edits_the_second_wins(app, new_client):
    admin, _ = await org_with_admin(new_client)
    await admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -6}}})
    await admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -7}}})
    moves = by_id((await admin.get("/api/rules")).json())
    assert moves["evades_direct_question"]["deltas"] == {"trust": -7}
