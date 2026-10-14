"""HTTP body and browser policies, including early failures and streaming responses."""

import asyncio

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_SECONDS = 30
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
)


def security_headers(scope: Scope) -> dict[str, str]:
    path = scope["path"].removeprefix(scope.get("root_path", ""))
    headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": CSP,
    }
    if (path == "/api" or path.startswith("/api/")) and not path.endswith("/cover-image"):
        headers["Cache-Control"] = "no-store"
    if scope.get("scheme") == "https":
        headers["Strict-Transport-Security"] = "max-age=86400"
    return headers


class HttpPolicy:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"].removeprefix(scope.get("root_path", ""))

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(security_headers(scope))
            await send(message)

        async def reject(status: int, detail: str) -> None:
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secure_send)

        headers = dict(scope["headers"])
        if scope["method"] in UNSAFE:
            if headers.get(b"x-requested-with") != b"nlab":
                await reject(403, "Missing header X-Requested-With: nlab")
                return
            limit = 8_000_000 if path == "/api/scenarios/builder/picture" else 1_000_000
            body = bytearray()
            try:
                async with asyncio.timeout(MAX_BODY_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > limit:
                            await reject(413, "Request body is too large")
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await reject(408, "Request body deadline exceeded")
                return
            scope.setdefault("state", {})["body_bytes"] = len(body)
            media_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
            json_body = (
                media_type == b"application/json"
                or media_type.startswith(b"application/")
                and media_type.endswith(b"+json")
                or not media_type
                and not path.endswith("/cover-image")
            )
            if json_body:
                try:
                    if "\x00" in body.decode("utf-8"):
                        raise ValueError("NUL byte in JSON")
                except (UnicodeDecodeError, ValueError):
                    await reject(422, "JSON documents must use UTF-8")
                    return
                depth = 0
                quoted = escaped = False
                for char in body:
                    if quoted:
                        if escaped:
                            escaped = False
                        elif char == 92:
                            escaped = True
                        elif char == 34:
                            quoted = False
                    elif char == 34:
                        quoted = True
                    elif char in (91, 123):
                        depth += 1
                        if depth > 32:
                            await reject(422, "JSON document depth exceeds 32")
                            return
                    elif char in (93, 125):
                        depth -= 1
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, secure_send)
        else:
            await self.app(scope, receive, secure_send)
