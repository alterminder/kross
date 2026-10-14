"""Production startup and HTTP policy use the same boundary as deployed traffic."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from nlab.api.app import create_app
from nlab.api.settings import Settings
from tests.api.test_spa import built
from tests.llm.fakes import FakeProvider


@pytest.mark.anyio
async def test_http_policy_covers_html_and_api_errors(tmp_path):
    app = create_app(
        Settings(_env_file=None, secret_key="test", static_dir=built(tmp_path)),
        providers={},
        llm=(FakeProvider([]), None),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://localhost") as http:
        html = await http.get("/")
        denied = await http.post("/api/nope", json={})
    assert html.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
    # Vite inlines small woff2 subsets as data: URIs; only font-src may allow data:.
    assert "font-src 'self' data:" in html.headers["content-security-policy"]
    assert html.headers["x-content-type-options"] == "nosniff"
    assert html.headers["strict-transport-security"] == "max-age=86400"
    assert denied.status_code == 403
    assert denied.headers["cache-control"] == "no-store"
    assert denied.headers["referrer-policy"] == "strict-origin-when-cross-origin"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("content", "expected"),
    [('{"notes":"' + "x" * 1_000_001 + '"}', 413), ("[" * 1000 + "0" + "]" * 1000, 422)],
    ids=["body-bytes", "json-depth"],
)
async def test_body_is_bounded_before_json_parsing_or_auth(content, expected):
    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.put(
            "/api/sessions/00000000-0000-0000-0000-000000000000/preparation",
            content=content,
            headers={"content-type": "application/json", "x-requested-with": "nlab"},
        )
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_json_depth_scanner_ignores_brackets_inside_escaped_strings():
    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.put(
            "/api/sessions/00000000-0000-0000-0000-000000000000/preparation",
            content=json.dumps({"notes": '[\\"[' * 100}),
            headers={"content-type": "application/json", "x-requested-with": "nlab"},
        )
    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize("content_type", [None, "application/problem+json"])
async def test_json_depth_limit_covers_all_fastapi_json_content_types(content_type):
    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    headers = {"x-requested-with": "nlab"}
    if content_type:
        headers["content-type"] = content_type
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.put(
            "/api/sessions/00000000-0000-0000-0000-000000000000/preparation",
            content="[" * 1000 + "0" + "]" * 1000,
            headers=headers,
        )
    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("content", ['{"notes":"hello"}'.encode("utf-16-le"), b'{"notes":"\xff"}'])
async def test_json_boundary_rejects_non_utf8_encodings(content):
    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.put(
            "/api/sessions/00000000-0000-0000-0000-000000000000/preparation",
            content=content,
            headers={"content-type": "application/json", "x-requested-with": "nlab"},
        )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"secret_key": "change-me-to-a-long-random-string"},
        {"secret_key": "CHANGE_ME_generate_openssl_rand_hex_32"},
        {"db_password": "CHANGE_ME_generate_a_different_openssl_rand_hex_32"},
        {"public_url": "http://training.example.org"},
        {"cookie_secure": False},
        {"session_retention_days": 0},
    ],
)
def test_production_refuses_example_or_insecure_settings(changes):
    values = dict(
        production=True,
        secret_key="K" * 48,
        db_user="nlab_app",
        db_password="P" * 48,
        public_url="https://training.example.org",
        session_retention_days=365,
    )
    values.update(changes)
    settings = Settings(_env_file=None, **values)
    with pytest.raises(ValueError):
        create_app(settings, providers={}, llm=(FakeProvider([]), None))


@pytest.mark.anyio
async def test_validation_errors_do_not_echo_sensitive_or_oversized_inputs():
    from nlab.api.deps import get_caller

    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    app.dependency_overrides[get_caller] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.post(
            "/api/invites/preview",
            json={"token": "PRIVATE_NOTE_MARKER" * 100},
            headers={"x-requested-with": "nlab"},
        )
    assert response.status_code == 422
    assert "PRIVATE_NOTE_MARKER" not in response.text
    assert len(response.content) < 2000


@pytest.mark.anyio
async def test_unexpected_api_failure_has_safe_body_and_security_headers():
    from nlab.api.deps import get_db

    async def unavailable_db():
        raise RuntimeError("DATABASE_SECRET_MARKER")

    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    app.dependency_overrides[get_db] = unavailable_db
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://localhost"
    ) as http:
        response = await http.get("/api/health")
    assert response.status_code == 500
    assert "DATABASE_SECRET_MARKER" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.anyio
async def test_slow_request_body_has_a_total_deadline(monkeypatch):
    import asyncio

    from nlab.api import http_policy

    monkeypatch.setattr(http_policy, "MAX_BODY_SECONDS", 0.02, raising=False)

    async def delayed_body():
        yield b"{"
        await asyncio.sleep(0.1)
        yield b"}"

    app = create_app(Settings(_env_file=None, secret_key="test"), providers={}, llm=(FakeProvider([]), None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.post(
            "/api/auth/guest",
            content=delayed_body(),
            headers={"content-type": "application/json", "x-requested-with": "nlab"},
        )
    assert response.status_code == 408
    assert response.headers["cache-control"] == "no-store"
