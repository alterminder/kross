from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from nlab.db import usage
from nlab.db.auth_sessions import utcnow
from tests.api.support import SUPERADMIN, sign_in
from tests.api.test_limits import limit, spend

pytestmark = pytest.mark.anyio


async def test_superadmins_see_usage_by_day_model_and_org(app, new_client):
    limit(app, model_prices={"deepseek-flash": (0.5, 2.0)}, daily_spend_ceiling_usd=10.0)
    root = new_client()
    root_me = await sign_in(root, "root", SUPERADMIN)
    alice = new_client()
    alice_me = await sign_in(alice, "alice", "alice@example.org")
    await spend(app, alice_me, tokens_in=1_000_000, tokens_out=1_000_000, model="deepseek-flash")
    await spend(app, root_me, tokens_in=10, model="other")
    await spend(app, alice_me, tokens_in=500, model="deepseek-flash", when=utcnow() - timedelta(days=2))
    report = (await root.get("/api/admin/usage?days=7")).json()
    assert report["ceiling_usd"] == 10.0 and report["spent_today_usd"] == pytest.approx(2.5)
    flash = next(row for row in report["models"] if row["model"] == "deepseek-flash")
    assert flash["calls"] == 2 and flash["tokens_in"] == 1_000_500
    assert sum(day["calls"] for day in report["days"]) == 3 and len(report["days"]) == 2
    assert [day["day"] for day in report["days"]] == [  # exact UTC date labels, oldest first
        (utcnow() - timedelta(days=2)).date().isoformat(),
        utcnow().date().isoformat(),
    ]
    today = {row["org_id"]: row for row in report["orgs_today"]}
    assert today[alice_me["active_org"]["id"]]["cost_usd"] == pytest.approx(2.5)


async def test_a_price_change_reprices_existing_rows(app, new_client):
    root = new_client()
    me = await sign_in(root, "root", SUPERADMIN)
    await spend(app, me, tokens_in=1_000_000, model="m")
    limit(app, model_prices={"m": (1.0, 0.0)})
    first = (await root.get("/api/admin/usage")).json()
    assert first["spent_today_usd"] == pytest.approx(1.0)
    limit(app, model_prices={"m": (2.0, 0.0)})
    second = (await root.get("/api/admin/usage")).json()
    assert second["spent_today_usd"] == pytest.approx(2.0)  # the same rows, read at the new price


async def test_rows_older_than_days_are_excluded(app, new_client):
    root = new_client()
    me = await sign_in(root, "root", SUPERADMIN)
    await spend(app, me, tokens_in=1, when=utcnow() - timedelta(days=10))
    await spend(app, me, tokens_in=1)
    seven = (await root.get("/api/admin/usage?days=7")).json()
    assert sum(day["calls"] for day in seven["days"]) == 1
    thirty = (await root.get("/api/admin/usage?days=30")).json()
    assert sum(day["calls"] for day in thirty["days"]) == 2


async def test_utc_day_boundaries_and_read_time_prices(app, new_client, monkeypatch):
    """Days are UTC days, whatever the database session's timezone; prices apply at read time."""
    now = datetime(2030, 1, 2, 0, 1, tzinfo=UTC)
    monkeypatch.setattr(usage, "utcnow", lambda: now)
    root = new_client()
    me = await sign_in(root, "root", SUPERADMIN)
    await spend(app, me, tokens_in=900, model="p", when=now.replace(day=1, hour=23, minute=59))  # just before midnight
    await spend(app, me, tokens_in=10, tokens_out=5, model="p", when=now.replace(minute=0))  # just after
    prices = {"p": (1_000_000, 2_000_000)}  # 1 USD per input token, 2 per output token
    async with app.state.sessionmaker() as db:
        await db.execute(text("SET TIME ZONE 'America/Los_Angeles'"))
        today = await usage.usage_since(db, usage.start_of_day(now), prices)
        assert (today.calls, today.tokens, today.cost_usd) == (1, 15, 20)
        days, models, orgs = await usage.usage_report(db, 2, prices)
        assert [(row.day, row.tokens_in) for row in days] == [("2030-01-01", 900), ("2030-01-02", 10)]
        assert orgs[0].tokens == 15 and models[0].cost_usd == 920
        repriced = await usage.usage_since(db, usage.start_of_day(now), {"p": (0.0, 0.0)})
        assert repriced.cost_usd == 0


async def test_only_superadmins_see_usage(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.get("/api/admin/usage")).status_code == 403
