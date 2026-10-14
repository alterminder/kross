"""Tables for accounts, orgs, memberships, invites, sign-in sessions, the scenario library and the usage ledger."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict[str, Any]: JSONB, list[dict[str, Any]]: JSONB}


class Role(StrEnum):
    admin = "admin"
    member = "member"


ROLE = Enum(Role, name="org_role", values_callable=lambda roles: [role.value for role in roles])


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str] = mapped_column(String(200))
    is_superadmin: Mapped[bool] = mapped_column(default=False)
    is_guest: Mapped[bool] = mapped_column(default=False)  # an anonymous visitor trying the app: see nlab.api.guest
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Identity(Base):
    """One provider account (provider + subject) that signs in as a user."""

    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Org(Base):
    __tablename__ = "orgs"
    __table_args__ = (Index("uq_orgs_system", "is_system", unique=True, postgresql_where=text("is_system")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    personal_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )  # set only for a user's personal org
    is_system: Mapped[bool] = mapped_column(default=False)  # holds the curated public content (seeded later)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[Role] = mapped_column(ROLE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[Role] = mapped_column(ROLE, default=Role.member)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime]
    max_uses: Mapped[int]
    uses: Mapped[int] = mapped_column(default=0)
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuthSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 hash is stored."""

    __tablename__ = "auth_sessions"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # the identity that authenticated this session: admin rights follow it, never any identity on the account.
    # Null (guests, pre-migration sessions) fails admin closed.
    identity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("identities.id", ondelete="CASCADE"))
    active_org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orgs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime]
    expires_at: Mapped[datetime]


class Visibility(StrEnum):
    private = "private"
    org = "org"
    public = "public"


VISIBILITY = Enum(Visibility, name="scenario_visibility", values_callable=lambda kinds: [kind.value for kind in kinds])


class Scenario(Base):
    """A scenario in the library. Its content lives in versions; `current_version` names the latest."""

    __tablename__ = "scenarios"
    __table_args__ = (
        Index(
            "uq_scenarios_curated_slug",
            "slug",
            unique=True,
            postgresql_where=text("curated AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    visibility: Mapped[Visibility] = mapped_column(VISIBILITY, default=Visibility.private)
    curated: Mapped[bool] = mapped_column(default=False)  # set only by the seed's upsert_curated
    slug: Mapped[str] = mapped_column(String(80))  # the content's own id, e.g. s01_idp_camp_access
    title: Mapped[str] = mapped_column(String(300))
    cover: Mapped[str] = mapped_column(String(40))
    current_version: Mapped[int] = mapped_column(default=1)
    submitted_at: Mapped[datetime | None]  # set when the owner asks the org's admins to publish it
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None]


class ScenarioVersion(Base):
    """Immutable content of one save. Play sessions (Plan E) pin a version."""

    __tablename__ = "scenario_versions"
    __table_args__ = (UniqueConstraint("scenario_id", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    number: Mapped[int]
    content: Mapped[dict[str, Any]]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ScenarioCoverImage(Base):
    """A scenario's custom card cover (WebP bytes). Never loaded when listing scenarios."""

    __tablename__ = "scenario_cover_images"

    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())  # the cache-buster the frontend uses


class RuleVersion(Base):
    """One save of an org's edits to the move dial changes. The highest `number` is the org's current rules."""

    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("org_id", "number", name="uq_rule_versions_org_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    number: Mapped[int]
    overrides: Mapped[dict[str, Any]]  # RuleOverrides.moves: {move_id: {dial: delta}}
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LlmCall(Base):
    """The usage ledger: one row per model call. No foreign keys: deleting an account keeps the counts."""

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    outcome: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(default=1)
    quote_rejections: Mapped[int] = mapped_column(default=0)
    reservation_id: Mapped[uuid.UUID | None]  # the budget reservation that paid: excluded from quota sums
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class BudgetReservation(Base):
    """Conservative hold for one billed model call: created before the call reaches the provider, closed in the same
    commit as the call's ledger row. No foreign keys (as LlmCall): deleting an account keeps the accounting. Open
    rows count toward the daily limits at their full reserved size, so unknown usage is never free and a call whose
    outcome is unknown keeps its hold for the day."""

    __tablename__ = "budget_reservations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    reserved_in: Mapped[int] = mapped_column(BigInteger)
    reserved_out: Mapped[int] = mapped_column(BigInteger)
    used_in: Mapped[int] = mapped_column(BigInteger, default=0)  # settled actuals; only written with state='settled'
    used_out: Mapped[int] = mapped_column(BigInteger, default=0)
    state: Mapped[str] = mapped_column(String(10), default="open")  # open (charged at the reservation) | settled
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    closed_at: Mapped[datetime | None]


class DailyAdmission(Base):
    """One durable daily counter per (day, scope, key): session starts, guest signups and coach questions. No foreign
    keys, so deleting transcripts or accounts never restores an allowance."""

    __tablename__ = "daily_admissions"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), primary_key=True)  # session_start | guest_signup | ...
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # user or session id, or a visitor's address
    count: Mapped[int] = mapped_column(BigInteger, default=0)


class StorageBucket(Base):
    __tablename__ = "storage_buckets"

    scope: Mapped[str] = mapped_column(String(10), primary_key=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # no FK: deletion never restores allowance
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    writes: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_written: Mapped[int] = mapped_column(BigInteger, default=0)


class TurnComment(Base):
    """A trainer's note on one turn. Watchers only: the player never sees comments."""

    __tablename__ = "turn_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("play_sessions.id", ondelete="CASCADE"), index=True)
    turn: Mapped[int]
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Mode(StrEnum):
    solo = "solo"
    playtest = "playtest"


class Status(StrEnum):
    active = "active"
    ended = "ended"


MODE = Enum(Mode, name="play_mode", values_callable=lambda items: [item.value for item in items])
STATUS = Enum(Status, name="play_status", values_callable=lambda items: [item.value for item in items])


class PlaySession(Base):
    """One run of a scenario by one player. Pins the scenario version and the effective rules at start."""

    __tablename__ = "play_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenario_versions.id", ondelete="CASCADE"))
    mode: Mapped[Mode] = mapped_column(MODE)
    status: Mapped[Status] = mapped_column(STATUS, default=Status.active)
    rules: Mapped[dict[str, Any]]  # raw behaviour rules with the org's edits applied, as at start
    engine_state: Mapped[dict[str, Any]]
    turn_in_progress: Mapped[datetime | None]  # the turn claim; see nlab.db.sessions.claim_turn
    debrief: Mapped[dict[str, Any] | None]
    debrief_status: Mapped[str | None] = mapped_column(String(12))  # pending | ready | failed | unavailable
    preparation: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    reflection: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]


class Turn(Base):
    """Row 0 holds the counterpart's opening line; row n the n-th trainee message and what followed it."""

    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("session_id", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("play_sessions.id", ondelete="CASCADE"), index=True)
    number: Mapped[int]
    trainee_text: Mapped[str | None] = mapped_column(Text)
    reply_text: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[dict[str, Any] | None]
    engine_state_after: Mapped[dict[str, Any]]
    events: Mapped[list[dict[str, Any]]]
    counterpart_request: Mapped[dict[str, Any] | None]  # exactly what the counterpart model received
    scores: Mapped[dict[str, Any] | None]
    scoring_started_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
