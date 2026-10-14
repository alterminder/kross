"""No database transaction may sit open while a model call runs (docs/architecture/README.md, step 2: "No
database transaction stays open during model calls"). The probe reads pg_stat_activity from inside every fake model
call: any backend that is 'idle in transaction' there is a connection the app left hanging over the call."""

import asyncpg
import pytest

from nlab.db.models import PlaySession
from tests.api.conftest import TEST_URL
from tests.api.fakes import ScriptedModel
from tests.api.support import PLAY_CONFIG, card_id, say, seed_curated, settle, sign_in, start_play

pytestmark = pytest.mark.anyio
PG = TEST_URL.replace("postgresql+asyncpg://", "postgresql://")


class Probe(ScriptedModel):
    """Records the idle-in-transaction backends every model call sees."""

    def __init__(self) -> None:
        super().__init__()
        self.saw: list[tuple[str, list[str]]] = []

    async def _look(self, role: str) -> None:
        connection = await asyncpg.connect(PG)
        try:
            rows = await connection.fetch(
                "SELECT query FROM pg_stat_activity WHERE datname = current_database() "
                "AND state = 'idle in transaction' AND pid <> pg_backend_pid()"
            )
        finally:
            await connection.close()
        self.saw.append((role, [str(row["query"])[:90] for row in rows]))

    async def complete(self, config, request, schema=None, json=False):
        await self._look(request.role)
        return await super().complete(config, request, schema, json)

    async def stream(self, config, request):
        await self._look("counterpart")
        async for part in super().stream(config, request):
            yield part


async def dials(app, session, **changes):
    async with app.state.sessionmaker() as db:
        row = await db.get_one(PlaySession, session["id"])
        state = dict(row.engine_state)
        state["dials"] = {**state["dials"], **changes}
        row.engine_state = state
        await db.commit()


async def test_no_transaction_stays_open_during_a_model_call(app, new_client):
    model = Probe()
    app.state.llm = (model, PLAY_CONFIG)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")

    # classifier, counterpart, grant: a partial outcome is granted mid-conversation, so no end work races the probes
    session = await start_play(alice, await card_id(alice, "checkpoint"))
    await dials(app, session, trust=50, rigidity=65, hostility=60)  # safe_next_step in range, passage not
    await say(alice, session["id"], "We carry food and medicine.")  # the offer goes on the table
    await settle(app)  # the scorer of turn 1 is done before turn 2 starts
    model.answers["classifier"].append('{"asked_for_goal": true}')
    model.replies.append(["Very well. I will confirm the procedure."])
    model.answers["grant"].append('{"granted": true, "quote": "I will confirm the procedure."}')
    await say(alice, session["id"], "Yes, please confirm the procedure.")  # classifier + counterpart + grant
    await settle(app)  # the scorer of turn 2 (evaluator)

    # debrief: the scorer is done before the end, so only finish_session's own calls run
    ended = await start_play(alice, await card_id(alice, "camp"))
    await say(alice, ended["id"], "Hello.")
    await settle(app)
    assert (await alice.post(f"/api/sessions/{ended['id']}/end")).status_code == 200
    await settle(app)

    assert {role for role, _ in model.saw} >= {"classifier", "counterpart", "grant", "evaluator", "debrief"}
    for role, queries in model.saw:
        assert queries == [], f"the {role} call ran with a transaction open: {queries}"
