"""Serves the built frontend: its static folders, and index.html for every other path outside /api so the
browser's router takes over. <base href> is set to the mount path, so a sub-path deployment (NLAB_ROOT_PATH) works
with the same build: every URL in the frontend is relative to it."""

import html
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = '<base href="/" />'

mimetypes.add_type("image/webp", ".webp")  # minimal containers ship a mime.types without webp


def mount_frontend(app: FastAPI, static_dir: Path, root_path: str) -> None:
    page = (static_dir / "index.html").read_text()
    if BASE not in page:
        raise RuntimeError(f"{static_dir}/index.html has no {BASE}: build the frontend with `npm run build`")
    index = page.replace(BASE, f'<base href="{html.escape(root_path.rstrip("/"))}/" />', 1)
    for folder in ("assets", "covers"):
        app.mount(f"/{folder}", StaticFiles(directory=static_dir / folder, check_dir=False), name=folder)

    @app.get("/{path:path}", include_in_schema=False)
    async def app_page(path: str) -> HTMLResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)  # an unknown API path stays a JSON 404, not a page
        return HTMLResponse(index, headers={"Cache-Control": "no-cache"})
