"""Deployment configuration from NLAB_* environment variables. Secrets never reach the database or the browser."""

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from nlab.llm import LLMConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NLAB_", env_file=".env", extra="ignore")

    database_url: str | None = None  # wins when set; otherwise built from the db_* fields below
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "nlab"
    db_password: SecretStr | None = None
    db_name: str = "nlab"
    secret_key: SecretStr  # signs the short-lived cookie that carries OIDC state during sign-in
    production: bool = False  # forced on by the image and compose.yml: invalid security settings prevent startup
    public_url: str = "http://localhost:8000"
    cookie_secure: bool = True
    session_idle_hours: float = Field(8, gt=0, allow_inf_nan=False)
    session_max_days: float = Field(7, gt=0, allow_inf_nan=False)
    superadmin_identities: dict[str, list[str]] = {}  # NLAB_SUPERADMIN_IDENTITIES (JSON): provider -> stable subjects
    superadmin_emails: str = ""  # deprecated: grants nobody, fails closed. Migrate to superadmin_identities.
    content_dir: Path = Path(__file__).resolve().parents[4] / "content"  # the repository's content/ folder
    allow_multiple_counterparts: bool = False  # generation only; existing scenarios keep their actors

    # Daily limits (UTC days); 0 switches a limit off. Placeholders until real use is measured.
    limit_user_sessions_per_day: int = Field(30, ge=0)
    limit_user_tokens_per_day: int = Field(1_000_000, ge=0)
    limit_org_tokens_per_day: int = Field(10_000_000, ge=0)
    daily_spend_ceiling_usd: float = Field(25.0, ge=0, allow_inf_nan=False)
    model_prices: dict[str, tuple[float, float]] = {}  # model -> (USD per 1M input tokens, USD per 1M output tokens)
    # Guest play: an anonymous visitor starts at once, with no sign-in. Off unless the operator turns it on. Guests may
    # only play curated scenarios alone, and have their own daily caps on top of the general ones (0 switches one off).
    guest_play: bool = False
    guest_session_hours: float = Field(24, gt=0, le=24, allow_inf_nan=False)  # purge assumes at most one day
    guest_limit_sessions_per_day: int = Field(3, ge=0)
    guest_limit_tokens_per_day: int = Field(150_000, ge=0)
    guest_limit_total_tokens_per_day: int = Field(2_000_000, ge=0)
    guest_limit_signups_per_day: int = Field(200, ge=0)
    guest_limit_signups_per_ip_per_day: int = Field(20, ge=1)
    coach_questions_per_session: int = Field(10, ge=0)  # 0 switches the cap off
    max_concurrent_model_calls: int = Field(16, ge=1)
    max_concurrent_paid_per_user: int = Field(4, ge=1)
    background_max_concurrent: int = Field(8, ge=1)
    background_max_pending: int = Field(64, ge=1)
    session_retention_days: int = Field(0, ge=0)  # 0 keeps play sessions forever in development
    limit_user_writes_per_day: int = Field(500, ge=1)
    limit_org_writes_per_day: int = Field(5000, ge=1)
    limit_total_writes_per_day: int = Field(20_000, ge=1)
    limit_user_storage_bytes: int = Field(1_000_000_000, ge=1)
    limit_org_storage_bytes: int = Field(5_000_000_000, ge=1)
    limit_total_storage_bytes: int = Field(20_000_000_000, ge=1)
    root_path: str = ""  # set when the app is served under a sub-path, e.g. /nlab
    static_dir: Path | None = None  # the built frontend (frontend/dist); unset in development, where Vite serves it

    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None

    oidc_name: str = "sso"
    oidc_label: str = "Organisation sign-in"
    oidc_metadata_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None

    def validate_deployment(self) -> None:
        if not self.production:
            return
        key = self.secret_key.get_secret_value()
        if len(key) < 32 or "change-me" in key.lower().replace("_", "-"):
            raise ValueError("NLAB_SECRET_KEY must be a unique random secret of at least 32 characters")
        url = urlsplit(self.public_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("NLAB_PUBLIC_URL must be the deployment's HTTPS URL")
        if "*" in url.hostname or url.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Production requires its public hostname in NLAB_PUBLIC_URL")
        if not self.cookie_secure:
            raise ValueError("Production requires NLAB_COOKIE_SECURE=true")
        if self.session_retention_days <= 0:
            raise ValueError("Production requires positive NLAB_SESSION_RETENTION_DAYS matching the privacy notice")
        password = (
            make_url(self.database_url).password
            if self.database_url
            else (self.db_password.get_secret_value() if self.db_password else "")
        )
        if not password or len(password) < 20 or "change-me" in password.lower().replace("_", "-"):
            raise ValueError("Production requires a unique random runtime database password")
        if self.superadmin_emails.strip():
            raise ValueError("Replace NLAB_SUPERADMIN_EMAILS with provider/subject NLAB_SUPERADMIN_IDENTITIES")

    def superadmin_policy(self) -> dict[str, set[str]]:
        """Who holds platform-admin rights: provider + stable subject. NLAB_SUPERADMIN_EMAILS is never consulted
        and grants nobody (it fails closed): a verified email is not an identity."""
        return {provider: set(subjects) for provider, subjects in self.superadmin_identities.items()}

    def validate_production(self, llm: "LLMConfig | None", painter: str | None = None) -> None:
        from nlab.api.limits import validate_production

        validate_production(self, llm, painter)

    def resolved_database_url(self) -> str:
        """database_url when set, else built from the db_* fields: a password with URL characters never needs
        encoding because it travels as a field, not inside a URL string."""
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value() if self.db_password else None,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)
