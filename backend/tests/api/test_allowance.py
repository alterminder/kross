"""GET /api/me/allowance: the caller's own tokens since 00:00 UTC against their personal daily limit."""

from datetime import UTC, datetime

import pytest

from tests.api.support import sign_in
from tests.api.test_guest import guest
from tests.api.test_limits import limit, spend

pytestmark = pytest.mark.anyio


async def allowance_of(client):
    response = await client.get("/api/me/allowance")
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_allowance_needs_a_session(new_client):
    assert (await new_client().get("/api/me/allowance")).status_code == 401


async def test_the_cutoff_counts_only_tokens_since_midnight_and_resets_at_the_next(app, new_client, monkeypatch):
    monkeypatch.setattr("nlab.api.account.utcnow", lambda: datetime(2027, 3, 4, 15, 0, tzinfo=UTC))
    limit(app, limit_user_tokens_per_day=1000)
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    await spend(app, me, tokens_in=5000, when=datetime(2027, 3, 3, 23, 59, 59, 999999, tzinfo=UTC))  # yesterday
    await spend(app, me, tokens_in=150, tokens_out=100, when=datetime(2027, 3, 4, 0, 0, tzinfo=UTC))  # counted
    allowance = await allowance_of(alice)
    assert allowance["used_tokens"] == 250  # only the row at/after midnight, not the 5000 before it
    assert allowance["limit_tokens"] == 1000
    assert allowance["remaining_percent"] == 75.0
    assert allowance["resets_at"] == "2027-03-05T00:00:00Z"  # the literal next midnight, not a computed guess


async def test_a_guest_is_held_to_the_smallest_enabled_personal_cap(app, new_client):
    """A guest is enforced against both the general user and the guest token cap (nlab.db.usage), so the reported
    cap is the smallest enabled one; only both disabled means unlimited."""
    cases = [
        # (user cap, guest cap, expected limit, expected remaining %)
        (100, 1000, 100, 70.0),  # the smaller general cap binds
        (1000, 0, 1000, 97.0),  # guest cap off: the general cap still applies
        (0, 500, 500, 94.0),  # general cap off: the guest cap still applies
        (0, 0, None, None),  # both off: unlimited
    ]
    for user_cap, guest_cap, expected_limit, expected_remaining in cases:
        limit(app, guest_play=True, limit_user_tokens_per_day=user_cap, guest_limit_tokens_per_day=guest_cap)
        client, me = await guest(app, new_client)
        await spend(app, me, tokens_in=30)
        allowance = await allowance_of(client)
        assert allowance["used_tokens"] == 30
        assert allowance["limit_tokens"] == expected_limit, (user_cap, guest_cap)
        assert allowance["remaining_percent"] == expected_remaining, (user_cap, guest_cap)


async def test_a_zero_limit_means_unlimited(app, new_client):
    limit(app, limit_user_tokens_per_day=0)
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    await spend(app, me, tokens_in=5000)
    allowance = await allowance_of(alice)
    assert allowance["used_tokens"] == 5000
    assert allowance["limit_tokens"] is None and allowance["remaining_percent"] is None


async def test_the_boundary_and_over_the_limit_both_clamp_to_zero(app, new_client):
    limit(app, limit_user_tokens_per_day=1000)
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    await spend(app, me, tokens_in=1000)  # exactly at the boundary
    at_limit = await allowance_of(alice)
    assert at_limit["used_tokens"] == 1000 and at_limit["remaining_percent"] == 0.0
    await spend(app, me, tokens_in=500)  # over it
    over = await allowance_of(alice)
    assert over["used_tokens"] == 1500 and over["remaining_percent"] == 0.0  # clamped, never negative


async def test_the_allowance_counts_only_the_callers_own_tokens(app, new_client):
    limit(app, limit_user_tokens_per_day=1000)
    alice = new_client()
    alice_me = await sign_in(alice, "alice", "alice@example.org")
    bob = new_client()
    bob_me = await sign_in(bob, "bob", "bob@example.org")
    await spend(app, bob_me, tokens_in=900)  # bob's spend must not show up in alice's ledger read
    await spend(app, alice_me, tokens_in=100)
    assert (await allowance_of(alice))["used_tokens"] == 100
    assert (await allowance_of(bob))["used_tokens"] == 900
