"""Production failures retain diagnostics without copying provider replies into logs."""

import logging

import httpx
import pytest
from authlib.integrations.starlette_client import OAuth

from nlab.api.app import create_app
from nlab.api.identity import OidcProvider
from nlab.api.pictures import Painter
from nlab.api.settings import Settings
from tests.api.support import card_id, say, seed_curated, settle, sign_in, start_play, use_model
from tests.api.test_auth import StubClient
from tests.llm.fakes import FakeProvider

PRIVATE_TEXT = "PRIVATE_PROVIDER_REPLY_REVIEW_MARKER"
PRIVATE_CAUSE = "PRIVATE_CAUSE_CHAIN_REVIEW_MARKER"


def private_failure(factory: type = RuntimeError) -> BaseException:
    """A failure whose message and cause chain both carry private markers."""
    error = factory(PRIVATE_TEXT)
    error.__cause__ = ValueError(PRIVATE_CAUSE)
    return error


@pytest.mark.anyio
async def test_production_background_errors_do_not_log_sensitive_exception_text(caplog, monkeypatch):
    for name in ("uvicorn.error", "nlab.api.background", "nlab.api.scoring"):
        monkeypatch.setattr(logging.getLogger(name), "filters", [])
    app = create_app(
        Settings(
            _env_file=None,
            production=True,
            secret_key="K" * 48,
            db_password="P" * 48,
            public_url="https://training.example.org",
            session_retention_days=365,
        ),
        providers={},
        llm=(FakeProvider([]), None),
        painter=Painter(None),
    )

    async def fails():
        raise RuntimeError("PRIVATE_PROVIDER_REPLY_MARKER")

    with caplog.at_level(logging.ERROR):
        app.state.background.spawn(fails())
        await app.state.background.drain(timeout=1)
    await app.state.engine.dispose()
    assert "Background task failed" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "PRIVATE_PROVIDER_REPLY_MARKER" not in caplog.text


@pytest.mark.anyio
async def test_a_turn_request_failure_logs_only_the_safe_type_and_context(app, new_client, caplog):
    model = use_model(app)
    model.answers["classifier"].append(private_failure())
    await seed_curated(app)
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    session = await start_play(client, await card_id(client, "camp"))
    with caplog.at_level(logging.WARNING):
        events = await say(client, session["id"], "Hello")
    assert events == [("error", {"detail": "The language model did not answer. Send your message again."})]
    assert "Classifier call failed" in caplog.text and "RuntimeError" in caplog.text
    assert PRIVATE_TEXT not in caplog.text and PRIVATE_CAUSE not in caplog.text


@pytest.mark.anyio
async def test_a_counterpart_stream_failure_logs_only_the_safe_type(app, new_client, caplog):
    model = use_model(app)
    model.replies.append(["Hello ", private_failure()])
    await seed_curated(app)
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    session = await start_play(client, await card_id(client, "camp"))
    with caplog.at_level(logging.WARNING):
        events = await say(client, session["id"], "Hello.")
    assert events == [
        ("reply", {"text": "Hello "}),
        ("error", {"detail": "The language model did not answer. Send your message again."}),
    ]
    assert "Counterpart call failed" in caplog.text and "RuntimeError" in caplog.text
    assert PRIVATE_TEXT not in caplog.text and PRIVATE_CAUSE not in caplog.text


@pytest.mark.anyio
async def test_a_scoring_failure_logs_only_the_safe_type_and_turn_context(app, new_client, caplog):
    model = use_model(app)
    model.answers["evaluator"].append(private_failure())
    await seed_curated(app)
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    session = await start_play(client, await card_id(client, "camp"))
    with caplog.at_level(logging.WARNING):
        await say(client, session["id"], "What worries you most?")
        await settle(app)
    assert f"Scoring turn 1 of session {session['id']}" in caplog.text
    assert "RuntimeError" in caplog.text
    assert PRIVATE_TEXT not in caplog.text and PRIVATE_CAUSE not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("route", "operation"),
    [("callback", "Sign-in through sso failed"), ("login", "Sign-in redirect through sso failed")],
)
@pytest.mark.parametrize("failure", [httpx.HTTPError, ValueError, RuntimeError], ids=["http", "value", "runtime"])
async def test_an_oidc_failure_logs_only_the_safe_type(app, new_client, caplog, route, operation, failure):
    provider = OidcProvider(OAuth(), "sso", "SSO", "https://issuer.example/metadata", "id", "secret")
    provider._client = StubClient(private_failure(failure))
    app.state.providers["sso"] = provider
    with caplog.at_level(logging.WARNING):
        response = await new_client().get(f"/api/auth/sso/{route}", params={"code": "x"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Sign-in failed; try again"}
    assert f"{operation} ({failure.__name__})" in caplog.text
    assert PRIVATE_TEXT not in caplog.text and PRIVATE_CAUSE not in caplog.text
