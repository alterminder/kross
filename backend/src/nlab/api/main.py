"""ASGI entry point: `uv run uvicorn nlab.api.main:app`. Settings come from NLAB_* environment variables."""

from nlab.api.app import create_app

app = create_app()
