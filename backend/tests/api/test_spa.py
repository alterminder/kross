"""The built frontend is served next to the API, with <base href> set to the mount path."""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nlab.api.app import create_app
from nlab.api.settings import Settings
from tests.llm.fakes import FakeProvider as FakeLLM

pytestmark = pytest.mark.anyio


def built(folder: Path) -> Path:
    (folder / "assets").mkdir()
    (folder / "covers").mkdir()
    (folder / "index.html").write_text('<html><head><base href="/" /></head><body><div id="root"></div></body></html>')
    (folder / "assets" / "app.js").write_text("console.log('app')")
    (folder / "covers" / "field.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    return folder


# /api/health touches the database: the dev Postgres (compose.dev.yml) serves on 5433
TEST_DB = os.environ.get("NLAB_TEST_DATABASE_URL", "postgresql+asyncpg://nlab:nlab@localhost:5433/nlab")


def client(static_dir: Path | None, root_path: str = "") -> AsyncClient:
    settings = Settings(
        _env_file=None, secret_key="test", static_dir=static_dir, root_path=root_path, database_url=TEST_DB
    )
    app = create_app(settings, providers={}, llm=(FakeLLM([]), None))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_app_paths_get_index_html_with_the_mount_path(tmp_path: Path) -> None:
    async with client(built(tmp_path), "/nlab") as http:
        page = await http.get("/play/123")
        assert page.status_code == 200
        assert '<base href="/nlab/" />' in page.text
        assert page.headers["cache-control"] == "no-cache"
        assert (await http.get("/")).text == page.text
        assert (await http.get("/privacy")).text == page.text  # the public privacy notice is an app path too
        assert (await http.get("/assets/app.js")).text == "console.log('app')"
        assert (await http.get("/covers/field.webp")).headers["content-type"] == "image/webp"


async def test_unknown_api_paths_stay_json_404s(tmp_path: Path) -> None:
    async with client(built(tmp_path)) as http:
        response = await http.get("/api/nope")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
        assert (await http.get("/api/health")).status_code == 200


async def test_without_a_build_there_are_no_pages() -> None:
    async with client(None) as http:
        assert (await http.get("/")).status_code == 404


def test_a_build_without_the_base_tag_fails_at_start(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>")
    with pytest.raises(RuntimeError, match="base href"):
        create_app(
            Settings(_env_file=None, secret_key="test", static_dir=tmp_path), providers={}, llm=(FakeLLM([]), None)
        )
