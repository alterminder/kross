"""A local server for development and the browser tests. Never deploy it: anyone who reaches it signs in as anyone.
It binds 127.0.0.1, signs in with /api/auth/dev/login?as=<name> (no password; `admin` is a superadmin), serves
frontend/dist when it is built, and answers with a scripted model unless --real-llm. The scripted model cannot
draft scenarios from a brief; paste scenario YAML instead, or use --real-llm.

    cd backend && uv run python -m tests.dev_server [--fresh] [--database nlab_dev] [--port 8765]
        [--public-url http://localhost:5173] [--real-llm]
"""

import argparse
import asyncio
import os
import re
from pathlib import Path

import asyncpg
import uvicorn
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from nlab.api.app import create_app
from nlab.api.identity import providers_from
from nlab.api.llm_settings import default_llm
from nlab.api.seed import seed
from nlab.api.settings import Settings
from tests.api.fakes import FakeProvider, ScriptedModel
from tests.api.support import PLAY_CONFIG

BACKEND = Path(__file__).resolve().parents[1]
SERVER = os.environ.get("NLAB_DEV_DATABASE_SERVER", "postgresql+asyncpg://nlab:nlab@localhost:5433")


class DevSignIn(FakeProvider):
    """Signs in as ?as=<name>; the identity is made up from the name."""

    async def login(self, request: Request, redirect_uri: str) -> Response:
        name = request.query_params.get("as", "alice")
        if not re.fullmatch(r"[a-z0-9]{1,32}", name):
            raise HTTPException(400, "as= takes 1 to 32 lowercase letters or digits")
        return RedirectResponse(f"{redirect_uri}?sub={name}&name={name.title()}&email={name}@example.test&verified=1")


async def prepare_database(name: str, fresh: bool) -> str:
    connection = await asyncpg.connect(f"{SERVER.replace('+asyncpg', '')}/postgres")
    try:
        if fresh:
            await connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        if not await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()
    return f"{SERVER}/{name}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default="nlab_dev")
    parser.add_argument("--fresh", action="store_true", help="drop and recreate the database first")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--public-url", help="where the browser reaches the app (default http://127.0.0.1:PORT)")
    parser.add_argument("--real-llm", action="store_true", help="the model settings from the environment and .env")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]{1,63}", args.database):
        parser.error("--database takes lowercase letters, digits and _")
    url = asyncio.run(prepare_database(args.database, args.fresh))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    dist = BACKEND.parent / "frontend" / "dist"
    env_file = dotenv_values(BACKEND / ".env")  # Google keys and generation policy; the process environment wins
    google_id = os.environ.get("NLAB_GOOGLE_CLIENT_ID", env_file.get("NLAB_GOOGLE_CLIENT_ID"))
    google_secret = os.environ.get("NLAB_GOOGLE_CLIENT_SECRET", env_file.get("NLAB_GOOGLE_CLIENT_SECRET"))
    settings = Settings(
        _env_file=None,
        database_url=url,
        secret_key="dev-server-only",
        cookie_secure=False,
        public_url=args.public_url or f"http://127.0.0.1:{args.port}",
        superadmin_identities={"dev": ["admin"]},
        guest_play=True,  # the e2e test of the guest journey
        static_dir=dist if (dist / "index.html").exists() else None,
        google_client_id=google_id,
        google_client_secret=google_secret,
        allow_multiple_counterparts=os.environ.get(
            "NLAB_ALLOW_MULTIPLE_COUNTERPARTS", env_file.get("NLAB_ALLOW_MULTIPLE_COUNTERPARTS", "false")
        ),
    )
    asyncio.run(seed(settings))
    llm = default_llm() if args.real_llm else (ScriptedModel(), PLAY_CONFIG)
    providers = {"dev": DevSignIn("dev"), **providers_from(settings)}
    app = create_app(settings, providers=providers, llm=llm)
    print(
        "Scenario generation: "
        + ("multiple actors allowed" if settings.allow_multiple_counterparts else "one counterpart"),
        flush=True,
    )
    print(f"Sign in: {settings.public_url}/api/auth/dev/login?as=alice  (as=admin is a superadmin)", flush=True)
    if "google" in providers:
        print(f"Google sign-in: on; register {settings.public_url}/api/auth/google/callback", flush=True)
    else:
        print(
            "Google sign-in: off (set NLAB_GOOGLE_CLIENT_ID and NLAB_GOOGLE_CLIENT_SECRET in backend/.env)",
            flush=True,
        )
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
