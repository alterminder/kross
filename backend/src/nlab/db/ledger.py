"""The usage ledger: one row per model call, written in the caller's transaction."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.models import LlmCall
from nlab.llm import CallRecord, RoleName


def record_call(
    db: AsyncSession,
    record: CallRecord,
    *,
    user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
    session_id: uuid.UUID | None = None,
) -> None:
    db.add(
        LlmCall(
            user_id=user_id,
            org_id=org_id,
            session_id=session_id,
            role=record.role,
            model=record.model,
            tokens_in=record.tokens_in,
            tokens_out=record.tokens_out,
            latency_ms=record.latency_ms,
            outcome=record.outcome,
            attempts=record.attempts,
            reservation_id=record.reservation_ids[0] if record.reservation_ids else None,
            quote_rejections=record.quote_rejections,
        )
    )


def record_error(
    db: AsyncSession,
    role: RoleName,
    model: str,
    *,
    user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
    session_id: uuid.UUID | None = None,
) -> None:
    """One ledger row for a provider error that carries no CallRecord: a paid call stays visible to caps and cost
    reports even when it blew up (the plan: every model call of a session gets a row)."""
    db.add(LlmCall(user_id=user_id, org_id=org_id, session_id=session_id, role=role, model=model, outcome="error"))
