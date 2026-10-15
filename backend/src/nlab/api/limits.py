"""The daily limits as configured, and a start-up warning for a ceiling that cannot work."""

import logging
import math

from nlab.api.settings import Settings
from nlab.db.usage import Limits
from nlab.llm import LLMConfig

logger = logging.getLogger(__name__)


def limits_of(settings: Settings) -> Limits:
    return Limits(
        user_sessions_per_day=settings.limit_user_sessions_per_day,
        user_tokens_per_day=settings.limit_user_tokens_per_day,
        org_tokens_per_day=settings.limit_org_tokens_per_day,
        daily_spend_usd=settings.daily_spend_ceiling_usd,
        prices=settings.model_prices,
        guest_sessions_per_day=settings.guest_limit_sessions_per_day,
        guest_tokens_per_day=settings.guest_limit_tokens_per_day,
        guest_total_tokens_per_day=settings.guest_limit_total_tokens_per_day,
        guest_signups_per_day=settings.guest_limit_signups_per_day,
        guest_signups_per_ip_per_day=settings.guest_limit_signups_per_ip_per_day,
        max_concurrent_model_calls=settings.max_concurrent_model_calls,
        max_concurrent_paid_per_user=settings.max_concurrent_paid_per_user,
    )


def warn_about_prices(settings: Settings, config: LLMConfig | None, painter_model: str | None = None) -> None:
    """A spend ceiling only counts models with a price; say so at start instead of failing silently."""
    if config is None or not settings.daily_spend_ceiling_usd:
        return
    models = {config.default.model, *(role.model for role in config.roles.values())}
    if painter_model:
        models.add(painter_model)  # image spend counts too
    missing = sorted(model for model in models if model not in settings.model_prices)
    if missing:
        logger.warning(
            "NLAB_DAILY_SPEND_CEILING_USD is set but NLAB_MODEL_PRICES has no price for %s: their cost counts as 0",
            ", ".join(missing),
        )


def validate_production(settings: Settings, llm: LLMConfig | None, painter: str | None = None) -> None:
    """Production preflight for the spending ceiling: a ceiling that cannot price a configured model
    silently counts zero, so production must refuse to start with missing, negative or non-finite prices."""
    if not settings.production or not settings.daily_spend_ceiling_usd:
        return
    models: set[str] = set()
    if llm is not None:
        models = {llm.default.model, *(role.model for role in llm.roles.values())}
    if painter:
        models.add(painter)
    for model in sorted(models):
        price = settings.model_prices.get(model)
        if price is None:
            raise ValueError(f"NLAB_MODEL_PRICES has no price for {model}; a spending ceiling cannot count it")
        for value in price:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"NLAB_MODEL_PRICES[{model}] must be finite and non-negative, got {price!r}")
