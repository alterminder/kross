import pytest

from tests.api.support import card_id, seed_curated, sign_in, start_play

pytestmark = pytest.mark.anyio


async def test_saving_and_reading_preparation(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))

    # Initial state: default short set of modules, preparation is None
    assert session["preparation"] is None
    assert set(session["preparation_modules"]) == {
        "island_of_agreements",
        "level_and_narrative",
        "lines_and_options",
    }

    # Save preparation data
    prep_data = {
        "skipped": False,
        "island_of_agreements": {
            "agreed_facts": ["Convoy is ready"],
            "contested_facts": ["Camp needs"],
            "convergent_norms": ["Safety"],
            "divergent_norms": ["Control"],
        },
        "level_and_narrative": {
            "why": "Humanitarian mandate",
            "how": "Independent aid",
            "what": "Convoy delivery",
            "expected_level": "technical",
        },
        "lines_and_options": {
            "ideal_outcome": "Immediate unconditional access",
            "bottom_line": "Direct distribution control",
        },
    }
    saved = await alice.put(f"/api/sessions/{session['id']}/preparation", json=prep_data)
    assert saved.status_code == 200, saved.text
    session_after = saved.json()
    assert session_after["preparation"] == prep_data

    # Re-reading session also reflects preparation
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["preparation"] == prep_data


async def test_skipping_preparation(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))

    saved = await alice.put(f"/api/sessions/{session['id']}/preparation", json={"skipped": True})
    assert saved.status_code == 200
    assert saved.json()["preparation"]["skipped"] is True


async def test_another_user_cannot_save_preparation(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))

    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    forbidden = await bob.put(f"/api/sessions/{session['id']}/preparation", json={"skipped": True})
    assert forbidden.status_code == 404


async def test_ended_session_refuses_preparation(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))

    # End the session
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    assert ended.status_code == 200

    refused = await alice.put(f"/api/sessions/{session['id']}/preparation", json={"skipped": True})
    assert refused.status_code == 410


async def test_guest_can_save_and_skip_preparation(app, new_client):
    from tests.api.test_guest import guest

    await seed_curated(app)
    client, _ = await guest(app, new_client)
    session = await start_play(client, await card_id(client, "camp"))

    saved = await client.put(f"/api/sessions/{session['id']}/preparation", json={"skipped": True})
    assert saved.status_code == 200, saved.text
    assert saved.json()["preparation"]["skipped"] is True
