"""The FastAPI application: middleware, error mapping and routers."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from nlab.api import account, admin, auth, health, invites, knowledge, org, play, rules, scenarios, steer
from nlab.api.background import Background
from nlab.api.content import load_content
from nlab.api.http_policy import HttpPolicy, security_headers
from nlab.api.identity import IdentityProvider, providers_from
from nlab.api.limits import warn_about_prices
from nlab.api.llm_settings import default_llm
from nlab.api.pictures import Painter, painter_from_env
from nlab.api.settings import Settings
from nlab.api.spa import mount_frontend
from nlab.api.storage import write_limit
from nlab.db.engine import make_engine, make_sessionmaker
from nlab.db.errors import Conflict, Forbidden, Gone, LimitReached, NotFound
from nlab.engine import EngineError
from nlab.llm import LLMConfig, Provider
from nlab.llm.types import AdmissionDenied, InputTooLarge

ERROR_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
    Forbidden: 403,
    Conflict: 409,
    Gone: 410,
    EngineError: 422,
    LimitReached: 429,
    AdmissionDenied: 429,
    InputTooLarge: 422,
}
ROUTERS = [
    health.router,
    auth.router,
    account.router,
    org.router,
    invites.router,
    admin.router,
    scenarios.router,
    rules.router,
    play.router,
    steer.router,
    knowledge.router,
]
LOST_RACE = {"23505", "23503"}  # unique_violation, foreign_key_violation: the states a lost race produces

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    providers: Mapping[str, IdentityProvider] | None = None,
    llm: tuple[Provider, LLMConfig | None] | None = None,
    painter: Painter | None = None,
) -> FastAPI:
    """The app. Without arguments, settings come from NLAB_* variables and providers from the settings."""
    settings = settings or Settings()
    settings.validate_deployment()
    engine = make_engine(settings.resolved_database_url())

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            if settings.production:
                async with engine.connect() as connection:
                    unsafe_role = await connection.scalar(
                        text(
                            "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
                            "OR has_schema_privilege(current_user, 'public', 'CREATE') "
                            "OR has_database_privilege(current_user, current_database(), 'CREATE') "
                            "OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = pg_roles.oid) "
                            "FROM pg_roles WHERE rolname = current_user"
                        )
                    )
                    if unsafe_role:
                        raise ValueError("The production app must connect with its unprivileged runtime DB role")
            yield
        finally:
            # a restart may lose scoring; the session end redoes it
            with suppress(TimeoutError):
                await application.state.background.drain(timeout=10)
            await engine.dispose()

    app = FastAPI(title="KROSS", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.providers = dict(providers) if providers is not None else providers_from(settings)
    app.state.content = load_content(settings.content_dir)
    app.state.llm = llm if llm is not None else default_llm()
    app.state.painter = painter if painter is not None else painter_from_env()
    if (
        settings.production
        and isinstance(app.state.painter, Painter)
        and app.state.painter.available
        and app.state.painter.model != "gemini-3.1-flash-image"
    ):
        raise ValueError("IMAGE_MODEL needs reviewed token limits; production supports gemini-3.1-flash-image")
    settings.validate_production(app.state.llm[1], app.state.painter.model if app.state.painter.available else None)
    warn_about_prices(settings, app.state.llm[1], app.state.painter.model if app.state.painter.available else None)
    app.state.background = Background(settings.background_max_concurrent, settings.background_max_pending)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="nlab_oauth",
        max_age=600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    if settings.production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[
                h for h in (urlsplit(settings.public_url).hostname, "127.0.0.1", "localhost") if h is not None
            ],
        )
    app.add_middleware(HttpPolicy)
    for error, status in ERROR_STATUS.items():
        app.add_exception_handler(error, _handler(status))
    app.add_exception_handler(IntegrityError, _conflict)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _server_error)
    for router in ROUTERS:
        app.include_router(router, dependencies=[Depends(write_limit)])
    if settings.static_dir is not None:
        mount_frontend(app, settings.static_dir, settings.root_path)  # last: its catch-all must not shadow the API
    return app


async def _validation_error(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    detail = [
        {
            "type": error["type"],
            "loc": [part if isinstance(part, int) else _safe_text(str(part)) for part in error["loc"]],
            "msg": _safe_text(error["msg"]),
        }
        for error in exc.errors()[:50]
    ]
    return JSONResponse({"detail": detail}, status_code=422)


def _safe_text(value: str) -> str:
    return value.encode("utf-8", errors="replace").decode("utf-8")[:512]


async def _server_error(request: Request, _: Exception) -> Response:
    return JSONResponse({"detail": "Internal server error"}, status_code=500, headers=security_headers(request.scope))


def _handler(status: int) -> Callable[[Request, Exception], Awaitable[Response]]:
    async def handle(_: Request, exc: Exception) -> Response:
        return JSONResponse({"detail": str(exc)}, status_code=status)

    return handle


async def _conflict(_: Request, exc: Exception) -> Response:
    """A lost race (duplicate key, missing parent) is a 409 with a generic message. Any other integrity error is
    a code bug: re-raise it so it becomes a 500 with a traceback instead of masquerading as a user conflict."""
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) not in LOST_RACE:
        raise exc
    logger.warning("Database conflict (SQLSTATE %s)", getattr(orig, "sqlstate", "unknown"))
    return JSONResponse({"detail": "That change conflicts with the current state"}, status_code=409)
