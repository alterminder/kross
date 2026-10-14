import pytest

from nlab.db.models import ScenarioVersion
from tests.api.support import CURATED, SUPERADMIN, count, draft, join, org_with_admin, seed_curated, sign_in, token_of
from tests.api.test_limits import limit

pytestmark = pytest.mark.anyio


async def signed_in(new_client, sub="alice"):
    client = new_client()
    await sign_in(client, sub, f"{sub}@example.org")
    return client


async def test_everyone_sees_the_curated_scenarios_as_cards(app, new_client):
    await seed_curated(app)
    alice = await signed_in(new_client)
    cards = (await alice.get("/api/scenarios")).json()
    assert {card["title"] for card in cards} == {scenario["title"] for scenario in CURATED.values()}
    camp = next(card for card in cards if card["cover"] == "camp")
    assert camp["title"] == "Access to an IDP camp" and camp["visibility"] == "public"
    assert camp["difficulty"] == "intermediate" and camp["minutes"] == 20 and camp["skills"]
    assert not camp["can_edit"] and camp["version"] == 1


async def test_a_player_sees_the_brief_but_not_the_hidden_content(app, new_client):
    await seed_curated(app)
    alice = await signed_in(new_client)
    card = next(card for card in (await alice.get("/api/scenarios")).json() if card["cover"] == "checkpoint")
    detail = (await alice.get(f"/api/scenarios/{card['id']}")).json()
    assert detail["content"] is None and "objective" in detail["brief"]
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    assert (await root.get(f"/api/scenarios/{card['id']}")).json()["content"]["id"] == "s09_hostile_checkpoint"


async def test_a_new_scenario_is_private_to_its_author(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    made = await bob.post("/api/scenarios", json={"content": draft(), "cover": "field"})
    assert made.status_code == 201, made.text
    assert made.json()["visibility"] == "private" and made.json()["can_edit"]
    scenario_id = made.json()["id"]
    assert scenario_id in {card["id"] for card in (await bob.get("/api/scenarios")).json()}
    assert scenario_id not in {card["id"] for card in (await admin.get("/api/scenarios")).json()}
    assert (await admin.get(f"/api/scenarios/{scenario_id}")).status_code == 404


async def test_invalid_content_is_refused_with_field_paths(app, new_client):
    alice = await signed_in(new_client)
    bad = draft()
    bad["outcomes"][0]["when"] = {"trust_above": 1}
    refused = await alice.post("/api/scenarios", json={"content": bad})
    assert refused.status_code == 422
    assert any(issue["path"].startswith("outcomes.0.when") for issue in refused.json()["detail"])
    assert (await alice.post("/api/scenarios/validate", json={"content": bad})).json()
    assert (await alice.post("/api/scenarios/validate", json={"content": draft()})).json() == []


async def test_every_save_is_a_new_version(app, new_client):
    alice = await signed_in(new_client)
    scenario_id = (await alice.post("/api/scenarios", json={"content": draft()})).json()["id"]
    saved = await alice.put(
        f"/api/scenarios/{scenario_id}", json={"content": draft("Water point dispute, revised"), "cover": "camp"}
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 2 and body["title"] == "Water point dispute, revised" and body["cover"] == "camp"
    assert await count(app, ScenarioVersion) == 2


async def test_only_admins_publish_to_the_org_library(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    bobs = (await bob.post("/api/scenarios", json={"content": draft("Bob's")})).json()
    assert (await bob.post(f"/api/scenarios/{bobs['id']}/visibility", json={"visibility": "org"})).status_code == 403
    admins = (await admin.post("/api/scenarios", json={"content": draft("Admin's")})).json()
    published = await admin.post(f"/api/scenarios/{admins['id']}/visibility", json={"visibility": "org"})
    assert published.status_code == 204
    seen = (await bob.get(f"/api/scenarios/{admins['id']}")).json()
    assert seen["visibility"] == "org" and not seen["can_edit"] and seen["content"] is None
    assert (await bob.put(f"/api/scenarios/{admins['id']}", json={"content": draft()})).status_code == 403


async def test_only_a_superadmin_makes_a_scenario_public(app, new_client):
    admin, _ = await org_with_admin(new_client)
    made = (await admin.post("/api/scenarios", json={"content": draft()})).json()
    public = await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    assert public.status_code == 403
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    curated = (await root.post("/api/scenarios", json={"content": draft("Curated one")})).json()
    published = await root.post(f"/api/scenarios/{curated['id']}/visibility", json={"visibility": "public"})
    assert published.status_code == 204
    alice = await signed_in(new_client)
    assert curated["id"] in {card["id"] for card in (await alice.get("/api/scenarios")).json()}


async def test_org_scenarios_stay_inside_their_org(app, new_client):
    admin_a, _ = await org_with_admin(new_client, "Org A")
    admin_b, _ = await org_with_admin(new_client, "Org B")
    made = (await admin_a.post("/api/scenarios", json={"content": draft()})).json()
    await admin_a.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    assert made["id"] not in {card["id"] for card in (await admin_b.get("/api/scenarios")).json()}
    assert (await admin_b.get(f"/api/scenarios/{made['id']}")).status_code == 404
    assert (await admin_b.put(f"/api/scenarios/{made['id']}", json={"content": draft()})).status_code == 404
    assert (await admin_b.delete(f"/api/scenarios/{made['id']}")).status_code == 404


async def test_a_deleted_scenario_disappears_but_its_versions_stay(app, new_client):
    alice = await signed_in(new_client)
    scenario_id = (await alice.post("/api/scenarios", json={"content": draft()})).json()["id"]
    assert (await alice.delete(f"/api/scenarios/{scenario_id}")).status_code == 204
    assert (await alice.get(f"/api/scenarios/{scenario_id}")).status_code == 404
    assert scenario_id not in {card["id"] for card in (await alice.get("/api/scenarios")).json()}
    assert await count(app, ScenarioVersion) == 1


async def test_covers_and_schema(app, new_client):
    alice = await signed_in(new_client)
    assert {"field", "camp", "checkpoint", "school"} <= set((await alice.get("/api/scenarios/covers")).json())
    assert (
        "custom" not in (await alice.get("/api/scenarios/covers")).json()
    )  # themes only; the painting is its own tile
    assert (await alice.post("/api/scenarios", json={"content": draft(), "cover": "moon"})).status_code == 422
    schema = (await alice.get("/api/scenarios/schema")).json()
    assert "outcomes" in schema["properties"]
    assert schema["x-skills-vocabulary"] == list(app.state.content.skills_vocabulary)


async def test_a_painted_cover_marks_the_scenario_custom(app, new_client):
    """Uploading the final painting makes the builder's saved scenario use it; a theme pick can still switch away."""
    alice = await signed_in(new_client)
    made = (await alice.post("/api/scenarios", json={"content": draft(), "cover": "field"})).json()
    assert made["cover"] == "field" and made["cover_image_version"] is None
    webp = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 20  # the endpoint checks the container bytes, not the pixels
    put = await alice.put(f"/api/scenarios/{made['id']}/cover-image", content=webp)
    assert put.status_code == 204, put.text
    detail = (await alice.get(f"/api/scenarios/{made['id']}")).json()
    assert detail["cover"] == "custom" and detail["cover_image_version"]
    switched = (await alice.put(f"/api/scenarios/{made['id']}", json={"content": draft(), "cover": "camp"})).json()
    assert switched["cover"] == "camp" and switched["cover_image_version"], (
        "switching themes never deletes the painting"
    )


async def test_submit_flow_member_submits_admin_publishes(app, new_client):
    """The review's submit flow replaces probe P9 (an admin could never see an unsubmitted private scenario)."""
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    made = (await bob.post("/api/scenarios", json={"content": draft("Bob's")})).json()
    assert not made["submitted"]
    # before submission the admin cannot see it at all
    assert (await admin.get(f"/api/scenarios/{made['id']}")).status_code == 404
    assert (await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})).status_code == 404
    assert (await bob.post(f"/api/scenarios/{made['id']}/submit")).status_code == 204
    # now the admin sees it, marked submitted, can read it (to decide), but still cannot edit it
    seen = (await admin.get(f"/api/scenarios/{made['id']}")).json()
    assert seen["submitted"] and not seen["can_edit"] and seen["content"] is not None
    assert (await admin.put(f"/api/scenarios/{made['id']}", json={"content": draft()})).status_code == 403
    # the owner can still edit it
    assert (await bob.put(f"/api/scenarios/{made['id']}", json={"content": draft("Bob's v2")})).status_code == 200
    # a non-admin member of the same org never sees the submitted draft
    carol = await signed_in(new_client, "carol")
    await join(carol, admin)
    assert (await carol.get(f"/api/scenarios/{made['id']}")).status_code == 404
    # publish: members see it, the submitted mark is gone
    assert (await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})).status_code == 204
    published = (await carol.get(f"/api/scenarios/{made['id']}")).json()
    assert published["visibility"] == "org" and not published["submitted"]


async def test_only_admins_read_a_submitted_draft(app, new_client):
    """NEW-3 (decision: admins may READ a submitted draft, read-only): the author and the org's admins get the
    content while it awaits review; a non-admin member never does."""
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    made = (await bob.post("/api/scenarios", json={"content": draft("Bob's")})).json()
    await bob.post(f"/api/scenarios/{made['id']}/submit")
    assert (await admin.get(f"/api/scenarios/{made['id']}")).json()["content"] is not None
    carol = await signed_in(new_client, "carol")
    await join(carol, admin)
    assert (await carol.get(f"/api/scenarios/{made['id']}")).status_code == 404  # not her draft to review
    await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    assert (await carol.get(f"/api/scenarios/{made['id']}")).json()["content"] is None


async def test_an_admin_can_return_a_submitted_draft(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    made = (await bob.post("/api/scenarios", json={"content": draft()})).json()
    await bob.post(f"/api/scenarios/{made['id']}/submit")
    assert (await admin.post(f"/api/scenarios/{made['id']}/return")).status_code == 204
    assert (await admin.get(f"/api/scenarios/{made['id']}")).status_code == 404  # back to owner-only
    assert not (await bob.get(f"/api/scenarios/{made['id']}")).json()["submitted"]


async def test_submit_and_return_are_checked(app, new_client):
    admin_a, _ = await org_with_admin(new_client, "Org A")
    admin_b, _ = await org_with_admin(new_client, "Org B")
    bob = await signed_in(new_client, "bob")
    await join(bob, admin_a)
    made = (await bob.post("/api/scenarios", json={"content": draft()})).json()
    await bob.post(f"/api/scenarios/{made['id']}/submit")
    # another org's admin never sees it, submitted or not
    assert (await admin_b.get(f"/api/scenarios/{made['id']}")).status_code == 404
    assert (await admin_b.post(f"/api/scenarios/{made['id']}/return")).status_code == 404
    assert (
        await admin_b.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    ).status_code == 404
    # only the owner submits
    assert (await admin_a.post(f"/api/scenarios/{made['id']}/submit")).status_code == 403
    # a scenario in a personal org cannot be submitted
    own = (await bob.post("/api/scenarios", json={"content": draft("Own")})).json()
    me = (await bob.get("/api/me")).json()
    personal = next(o for o in me["orgs"] if o["personal"])
    assert (await bob.post("/api/orgs/active", json={"org_id": personal["id"]})).status_code == 204
    mine = (await bob.post("/api/scenarios", json={"content": draft("Mine", "mine")})).json()
    assert (await bob.post(f"/api/scenarios/{mine['id']}/submit")).status_code == 409
    assert own["id"] != mine["id"]


async def test_content_over_500_kb_is_refused(app, new_client):
    alice = await signed_in(new_client)
    big = draft()
    big["trainee_brief"]["situation"] = "x" * 600_000
    assert (await alice.post("/api/scenarios", json={"content": big})).status_code == 422
    assert (await alice.post("/api/scenarios/validate", json={"content": big})).status_code == 422
    made = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    assert (await alice.put(f"/api/scenarios/{made['id']}", json={"content": big})).status_code == 422


async def test_R8_the_cap_counts_utf8_bytes_not_escapes(app, new_client):
    """90,000 Arabic characters are 180 KB of UTF-8 (540 KB as unicode escapes) and must fit the
    500 KB cap, so ICRC content in Arabic, Russian or Ukrainian is not refused at a sixth of the stated size."""
    alice = await signed_in(new_client)
    content = draft()
    content["trainee_brief"]["situation"] = "ع" * 90_000
    saved = await alice.post("/api/scenarios", json={"content": content})
    assert saved.status_code == 201, (saved.status_code, str(saved.json())[:200])


async def test_R5_an_ownerless_org_scenario_cannot_be_made_private(app, new_client):
    """after the author deletes their account, private would hide the scenario from everyone and
    keep it forever; the admin is pointed at delete instead."""
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    made = (await bob.post("/api/scenarios", json={"content": draft()})).json()
    await bob.post(f"/api/scenarios/{made['id']}/submit")
    await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    assert (await bob.delete("/api/me")).status_code == 204
    moved = await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "private"})
    assert moved.status_code == 409 and "no author" in moved.json()["detail"], moved.text
    assert (await admin.get(f"/api/scenarios/{made['id']}")).status_code == 200  # still reachable as an org scenario


async def test_R4_a_submitted_draft_published_to_public_is_no_longer_submitted(app, new_client):
    """publishing straight to public must clear the submitted mark like every visibility change."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    created = await root.post("/api/admin/orgs", json={"name": "Org R"})
    assert created.status_code == 201, created.text
    await root.post(
        "/api/invites/accept",
        json={"token": token_of(created.json()["admin_invite_url"]), "acknowledged": True},
    )
    made = (await root.post("/api/scenarios", json={"content": draft()})).json()
    assert (await root.post(f"/api/scenarios/{made['id']}/submit")).status_code == 204
    assert (
        await root.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    ).status_code == 204
    card = (await root.get(f"/api/scenarios/{made['id']}")).json()
    assert card["visibility"] == "public" and not card["submitted"], card["submitted"]


async def test_R6_only_a_submitted_draft_can_be_returned(app, new_client):
    """POST /return answers 409 unless the scenario is a private, submitted draft."""
    admin, _ = await org_with_admin(new_client)
    made = (await admin.post("/api/scenarios", json={"content": draft()})).json()
    await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    returned = await admin.post(f"/api/scenarios/{made['id']}/return")
    assert returned.status_code == 409, returned.status_code
    private = (await admin.post("/api/scenarios", json={"content": draft("Private")})).json()
    assert (await admin.post(f"/api/scenarios/{private['id']}/return")).status_code == 409  # never submitted


async def test_a_copy_is_a_private_draft_with_a_new_id_and_title(app, new_client):
    alice = await signed_in(new_client)
    original = (await alice.post("/api/scenarios", json={"content": draft(), "cover": "camp"})).json()
    first = await alice.post(f"/api/scenarios/{original['id']}/duplicate")
    assert first.status_code == 201, first.text
    copy = first.json()
    assert copy["id"] != original["id"] and copy["visibility"] == "private" and copy["can_edit"]
    assert copy["title"] == "Water point dispute (copy)" and copy["cover"] == "camp" and copy["version"] == 1
    assert copy["content"]["id"] == "water_point_copy"
    second = (await alice.post(f"/api/scenarios/{original['id']}/duplicate")).json()
    assert second["content"]["id"] == "water_point_copy2"  # a taken id is never reused
    again = (await alice.post(f"/api/scenarios/{copy['id']}/duplicate")).json()
    assert again["content"]["id"] == "water_point_copy3" and again["title"] == "Water point dispute (copy) (copy)"
    assert {copy["id"], second["id"], again["id"]} <= {
        card["id"] for card in (await alice.get("/api/scenarios")).json()
    }


async def test_a_copy_needs_the_right_to_read_the_full_content(app, new_client):
    await seed_curated(app)
    alice = await signed_in(new_client)
    curated = next(card for card in (await alice.get("/api/scenarios")).json() if card["cover"] == "checkpoint")
    assert (await alice.post(f"/api/scenarios/{curated['id']}/duplicate")).status_code == 403
    admin, _ = await org_with_admin(new_client)
    made = (await admin.post("/api/scenarios", json={"content": draft()})).json()
    await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    assert (await bob.post(f"/api/scenarios/{made['id']}/duplicate")).status_code == 403
    assert (await admin.post(f"/api/scenarios/{made['id']}/duplicate")).status_code == 201
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    copied = await root.post(f"/api/scenarios/{curated['id']}/duplicate")
    assert copied.status_code == 201 and copied.json()["visibility"] == "private"
    assert copied.json()["content"]["id"] == "s09_hostile_checkpoint_copy"


async def test_a_long_id_is_cut_so_the_copy_fits_the_slug(app, new_client):
    alice = await signed_in(new_client)
    long_id = "x" * 80
    original = (await alice.post("/api/scenarios", json={"content": draft(scenario_id=long_id)})).json()
    copy = (await alice.post(f"/api/scenarios/{original['id']}/duplicate")).json()
    assert copy["content"]["id"] == "x" * 60 + "_copy"


async def test_the_editor_can_read_what_a_scenario_without_timing_does(app, new_client):
    alice = await signed_in(new_client)
    out = (await alice.get("/api/scenarios/timing-defaults")).json()
    assert [stage["id"] for stage in out["phases"]] == ["opening", "exploration", "closing"]
    assert out["phases"][0]["label"] == "Opening" and out["phases"][0]["instruction"].startswith("OPENING PHASE")
    assert out["warnings"] == [5, 1] and out["silence_after_seconds"] == 90


WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 20  # enough magic: RIFF....WEBP


async def test_a_custom_cover_round_trips_with_cache_headers(app, new_client):
    alice = await signed_in(new_client)
    scenario_id = (await alice.post("/api/scenarios", json={"content": draft()})).json()["id"]
    put = await alice.put(
        f"/api/scenarios/{scenario_id}/cover-image", content=WEBP, headers={"Content-Type": "image/webp"}
    )
    assert put.status_code == 204, put.text
    got = await alice.get(f"/api/scenarios/{scenario_id}/cover-image")
    assert got.status_code == 200
    assert got.content == WEBP
    assert got.headers["content-type"] == "image/webp"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["cache-control"] == "private, no-cache"  # access is re-checked on every use


async def test_a_chunked_upload_stops_at_the_cap(app, new_client):
    alice = await signed_in(new_client)
    scenario_id = (await alice.post("/api/scenarios", json={"content": draft()})).json()["id"]
    consumed: list[int] = []

    async def chunks():  # no Content-Length: the running count must stop the read
        for number in range(3):
            consumed.append(number)
            yield b"\x00" * (512 * 1024)

    response = await alice.put(
        f"/api/scenarios/{scenario_id}/cover-image", content=chunks(), headers={"Content-Type": "image/webp"}
    )
    assert response.status_code == 413
    assert consumed == [0, 1]  # the third 512 KB chunk is never read: consumption stops at 800 KB


async def test_a_cover_must_be_a_webp_under_800_kb(app, new_client):
    alice = await signed_in(new_client)
    scenario_id = (await alice.post("/api/scenarios", json={"content": draft()})).json()["id"]
    url = f"/api/scenarios/{scenario_id}/cover-image"
    assert (await alice.put(url, content=b"<svg onload=alert(1)>")).status_code == 422
    assert (await alice.put(url, content=WEBP + b"\x00" * (800 * 1024))).status_code == 413


async def test_only_an_editor_sets_the_cover(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = await signed_in(new_client, "bob")
    await join(bob, admin)
    published = (await admin.post("/api/scenarios", json={"content": draft()})).json()
    await admin.post(f"/api/scenarios/{published['id']}/visibility", json={"visibility": "org"})
    assert (await bob.put(f"/api/scenarios/{published['id']}/cover-image", content=WEBP)).status_code == 403
    hidden = (await admin.post("/api/scenarios", json={"content": draft("Hidden")})).json()
    assert (await bob.put(f"/api/scenarios/{hidden['id']}/cover-image", content=WEBP)).status_code == 404


async def test_a_guest_sees_only_public_custom_covers(app, new_client):
    limit(app, guest_play=True)
    alice = await signed_in(new_client)
    private = (await alice.post("/api/scenarios", json={"content": draft("Private")})).json()["id"]
    assert (await alice.put(f"/api/scenarios/{private}/cover-image", content=WEBP)).status_code == 204
    await seed_curated(app)
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    curated = next(card for card in (await root.get("/api/scenarios")).json() if card["cover"] == "checkpoint")
    assert (await root.put(f"/api/scenarios/{curated['id']}/cover-image", content=WEBP)).status_code == 204
    guest = new_client()
    assert (await guest.post("/api/auth/guest")).status_code == 204
    assert (await guest.get(f"/api/scenarios/{curated['id']}/cover-image")).status_code == 200
    assert (await guest.get(f"/api/scenarios/{private}/cover-image")).status_code == 404


async def test_a_duplicate_carries_the_cover_along(app, new_client):
    alice = await signed_in(new_client)
    original = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    assert (await alice.put(f"/api/scenarios/{original['id']}/cover-image", content=WEBP)).status_code == 204
    copy = (await alice.post(f"/api/scenarios/{original['id']}/duplicate")).json()
    got = await alice.get(f"/api/scenarios/{copy['id']}/cover-image")
    assert got.status_code == 200 and got.content == WEBP
    assert copy["cover"] == "custom" and copy["cover_image_version"]


async def test_cards_carry_the_cover_image_version(app, new_client):
    alice = await signed_in(new_client)
    made = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    assert made["cover_image_version"] is None  # no custom cover: the theme cover
    assert (await alice.put(f"/api/scenarios/{made['id']}/cover-image", content=WEBP)).status_code == 204
    card = next(card for card in (await alice.get("/api/scenarios")).json() if card["id"] == made["id"])
    first = card["cover_image_version"]
    assert first  # the cache-buster for the custom cover URL
    assert (await alice.put(f"/api/scenarios/{made['id']}/cover-image", content=WEBP + b"\x00" * 4)).status_code == 204
    assert (await alice.get(f"/api/scenarios/{made['id']}")).json()["cover_image_version"] != first  # URL changes
