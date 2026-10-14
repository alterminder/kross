"""Helpers for API tests."""

import copy
import json as jsonlib
import uuid
from dataclasses import replace
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select

from nlab.api.content import load_content
from nlab.db.models import LlmCall
from nlab.llm import LLMConfig, RoleConfig
from tests.conftest import CONTENT

SUPERADMIN = "root@example.org"


async def sign_in(
    client: AsyncClient,
    sub: str,
    email: str | None = None,
    *,
    verified: bool = True,
    name: str | None = None,
    provider: str = "fake",
) -> dict[str, Any]:
    """Signs the client in through the real login and callback routes; returns GET /api/me."""
    params = {"sub": sub, "email": email or "", "verified": "1" if verified else "0", "name": name or sub}
    login = await client.get(f"/api/auth/{provider}/login", params=params)
    assert login.status_code in (302, 303, 307), login.text
    callback = await client.get(login.headers["location"])
    assert callback.status_code == 303, callback.text
    me = await client.get("/api/me")
    assert me.status_code == 200, me.text
    return me.json()  # type: ignore[no-any-return]


async def count(app: FastAPI, model: Any) -> int:
    async with app.state.sessionmaker() as db:
        return int(await db.scalar(select(func.count()).select_from(model)) or 0)


def token_of(url: str) -> str:
    """Invite links are {public_url}/invite#<token>: the fragment carries the token."""
    return url.split("#", 1)[1]


async def org_with_admin(new_client: Any, name: str = "Red Cross Delegation") -> tuple[AsyncClient, str]:
    """A shared org created by the superadmin, with a fresh admin who joined through the admin invite."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    created = await root.post("/api/admin/orgs", json={"name": name})
    assert created.status_code == 201, created.text
    slug = name.lower().replace(" ", "-")
    admin = new_client()
    await sign_in(admin, f"admin-{slug}", f"admin-{slug}@example.org")
    accepted = await admin.post(
        "/api/invites/accept",
        json={"token": token_of(created.json()["admin_invite_url"]), "acknowledged": True},
    )
    assert accepted.status_code == 200, accepted.text
    return admin, created.json()["org_id"]


async def join(client: AsyncClient, admin: AsyncClient) -> None:
    """The admin invites; the client accepts. The client's active org becomes the admin's org."""
    invite = await admin.post("/api/org/invites", json={})
    assert invite.status_code == 201, invite.text
    accepted = await client.post(
        "/api/invites/accept", json={"token": token_of(invite.json()["url"]), "acknowledged": True}
    )
    assert accepted.status_code == 200, accepted.text


CURATED = {scenario["id"]: scenario for scenario in load_content(CONTENT).curated}


def draft(title: str = "Water point dispute", scenario_id: str = "water_point") -> dict[str, Any]:
    """A valid scenario of the author's own, derived from a curated one."""
    content = copy.deepcopy(CURATED["s01_idp_camp_access"])
    content["id"], content["title"] = scenario_id, title
    return content


async def seed_curated(app: FastAPI, content: Any = None) -> dict[str, str]:
    from nlab.api.seed import seed_database

    async with app.state.sessionmaker() as db:
        outcome = await seed_database(db, content or app.state.content)
        await db.commit()
        return outcome


def with_curated_title(app: FastAPI, scenario_id: str, suffix: str) -> Any:
    """The app's content with one curated scenario's title changed."""
    changed = tuple(
        {**scenario, "title": scenario["title"] + suffix} if scenario["id"] == scenario_id else scenario
        for scenario in app.state.content.curated
    )
    return replace(app.state.content, curated=changed)


PLAY_CONFIG = LLMConfig(default=RoleConfig(model="test-model", api_key=SecretStr("k"), first_word_seconds=0.5))


def use_model(app: FastAPI) -> Any:
    """Installs a ScriptedModel as the app's model and returns it."""
    from tests.api.fakes import ScriptedModel

    model = ScriptedModel()
    app.state.llm = (model, PLAY_CONFIG)
    return model


_CANONICAL_TITLES = {
    "camp": "Access to an IDP camp",
    "checkpoint": "Negotiating access at a hostile checkpoint",
    "detention": "Detention visit at a police station",
    "border": "Border crossing in no man's land",
    "school": "Negotiating safe access to education for children",
    "tripartite": "Tripartite Siege Access: Al-Mansoura Enclave",
}


async def card_id(client: AsyncClient, cover: str) -> str:
    cards = (await client.get("/api/scenarios")).json()
    canonical_title = _CANONICAL_TITLES.get(cover)
    if canonical_title:
        for card in cards:
            if card["title"] == canonical_title:
                return card["id"]
    return next(card["id"] for card in cards if card["cover"] == cover)


async def start_play(client: AsyncClient, scenario_id: str, mode: str = "solo") -> dict[str, Any]:
    started = await client.post("/api/sessions", json={"scenario_id": scenario_id, "mode": mode})
    assert started.status_code == 201, started.text
    return started.json()  # type: ignore[no-any-return]


async def say(client: AsyncClient, session_id: str, text: str) -> list[tuple[str, dict[str, Any]]]:
    """Sends one trainee message and returns the stream's events as (event, data) pairs."""
    events: list[tuple[str, dict[str, Any]]] = []
    async with client.stream("POST", f"/api/sessions/{session_id}/turns", json={"text": text}) as response:
        assert response.status_code == 200, (await response.aread()).decode()
        event = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((event, jsonlib.loads(line.removeprefix("data: "))))
    return events


async def nudge(client: AsyncClient, session_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Sends an inactivity nudge and returns the stream's events as (event, data) pairs."""
    events: list[tuple[str, dict[str, Any]]] = []
    async with client.stream("POST", f"/api/sessions/{session_id}/nudge") as response:
        assert response.status_code == 200, (await response.aread()).decode()
        event = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((event, jsonlib.loads(line.removeprefix("data: "))))
    return events


async def ask_coach(
    client: AsyncClient, session_id: str, question: str, history: list[dict[str, str]] | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """Sends a question to the Coach debrief assistant and returns the stream's events as (event, data) pairs."""
    events: list[tuple[str, dict[str, Any]]] = []
    payload = {"question": question, "history": history or []}
    async with client.stream("POST", f"/api/sessions/{session_id}/coach", json=payload) as response:
        assert response.status_code == 200, (await response.aread()).decode()
        event = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((event, jsonlib.loads(line.removeprefix("data: "))))
    return events


def reply_of(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(data["text"] for event, data in events if event == "reply")


def done_of(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    return next(data for event, data in events if event == "done")


async def settle(app: FastAPI) -> None:
    """Waits for background scoring and debriefs, at most 10 s."""
    await app.state.background.drain(timeout=10)


async def ledger(app: FastAPI, session_id: str) -> list[tuple[str, str]]:
    """The session's usage-ledger rows as (role, outcome), sorted. Rows without the session id never appear here."""
    async with app.state.sessionmaker() as db:
        rows = (
            await db.execute(select(LlmCall.role, LlmCall.outcome).where(LlmCall.session_id == uuid.UUID(session_id)))
        ).all()
    return sorted((str(role), str(outcome)) for role, outcome in rows)


PLAYER_SESSION_KEYS = {
    "id",
    "scenario_id",
    "title",
    "cover",
    "mode",
    "status",
    "turn",
    "turn_running",
    "brief",
    "transcript",
    "outcome",
    "debrief_status",
    "phase",
    "phases",
    "minutes_total",
    "seconds_left",
    "warning_minutes",
    "on_timeout",
    "silence_seconds",
    "preparation",
    "preparation_modules",
    "preparation_minutes",
    "reflection",
    "counterparts",
    "stakeholders",
    "active_interlocutor",
    "multiparty",
}
