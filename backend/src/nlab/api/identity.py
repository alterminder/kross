"""Sign-in providers. Google and an org's SSO both use OpenID Connect through the same Authlib code path."""

import logging
from typing import Protocol

from authlib.integrations.starlette_client import OAuth
from fastapi import Request, Response

from nlab.api.settings import Settings
from nlab.db.accounts import VerifiedIdentity

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"

logger = logging.getLogger(__name__)


class SignInFailed(Exception):
    pass


class IdentityProvider(Protocol):
    name: str
    label: str

    async def login(self, request: Request, redirect_uri: str) -> Response: ...

    async def identity(self, request: Request) -> VerifiedIdentity: ...


class OidcProvider:
    def __init__(self, oauth: OAuth, name: str, label: str, metadata_url: str, client_id: str, secret: str) -> None:
        self.name, self.label = name, label
        oauth.register(
            name=name,
            client_id=client_id,
            client_secret=secret,
            server_metadata_url=metadata_url,
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )
        self._client = oauth.create_client(name)

    async def login(self, request: Request, redirect_uri: str) -> Response:
        try:
            response: Response = await self._client.authorize_redirect(request, redirect_uri)
        except Exception as exc:  # not BaseException: a cancelled request must still propagate
            logger.warning("Sign-in redirect through %s failed (%s)", self.name, type(exc).__name__)
            raise SignInFailed(type(exc).__name__) from None  # the cause chain can carry provider text
        return response

    async def identity(self, request: Request) -> VerifiedIdentity:
        try:
            token = await self._client.authorize_access_token(request)
        except Exception as exc:  # not BaseException: a cancelled request must still propagate
            logger.warning("Sign-in through %s failed (%s)", self.name, type(exc).__name__)
            raise SignInFailed(type(exc).__name__) from None  # the cause chain can carry provider text
        claims = token.get("userinfo") or {}
        if not claims.get("sub"):
            raise SignInFailed("The provider returned no subject")
        return VerifiedIdentity(
            provider=self.name,
            subject=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=claims.get("email_verified") in (True, "true"),
            name=claims.get("name"),
        )


def providers_from(settings: Settings) -> dict[str, IdentityProvider]:
    """The providers this deployment configured: Google, a generic OIDC provider, or both."""
    oauth = OAuth()
    found: dict[str, IdentityProvider] = {}
    if settings.google_client_id and settings.google_client_secret:
        found["google"] = OidcProvider(
            oauth,
            "google",
            "Google",
            GOOGLE_METADATA,
            settings.google_client_id,
            settings.google_client_secret.get_secret_value(),
        )
    if settings.oidc_metadata_url and settings.oidc_client_id and settings.oidc_client_secret:
        found[settings.oidc_name] = OidcProvider(
            oauth,
            settings.oidc_name,
            settings.oidc_label,
            settings.oidc_metadata_url,
            settings.oidc_client_id,
            settings.oidc_client_secret.get_secret_value(),
        )
    return found
