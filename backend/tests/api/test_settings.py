"""The database URL: built from fields so a password never needs URL-encoding."""

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from nlab.api.settings import Settings


def test_a_password_with_url_characters_round_trips():
    settings = Settings(
        _env_file=None,
        secret_key="test-secret",
        db_host="db",
        db_password=SecretStr("ci@pa%40ss/w:rd"),
    )
    url = make_url(settings.resolved_database_url())
    assert url.password == "ci@pa%40ss/w:rd"  # %40 is a valid escape: a double-decode bug fails this
    assert (url.drivername, url.username, url.host, url.port, url.database) == (
        "postgresql+asyncpg",
        "nlab",
        "db",
        5432,
        "nlab",
    )


def test_an_explicit_database_url_wins():
    settings = Settings(_env_file=None, secret_key="test-secret", database_url="postgresql+asyncpg://example")
    assert settings.resolved_database_url() == "postgresql+asyncpg://example"


@pytest.mark.parametrize("ceiling", [float("nan"), float("inf"), -1.0])
def test_spend_ceiling_rejects_values_that_cannot_be_enforced(ceiling):
    with pytest.raises(ValueError):
        Settings(_env_file=None, secret_key="test", daily_spend_ceiling_usd=ceiling)
