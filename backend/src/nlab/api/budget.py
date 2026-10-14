"""Conservative admission for every billed model call.

`Budgeted` wraps any model provider at the shared enforcement boundary. Before each `complete`/`stream` invocation
(and before any native paint call, through `charge`/`reserve`) it admits the call in one short Postgres transaction:
a strict-fit check of the caller's remaining user/org/guest token caps and the deployment's spend ceiling against
the call's bounded worst case, the storage write allowance for its ledger rows, and then an open
`budget_reservations` hold. Settlement is one atomic UPDATE on the exact reservation id that records the actual
usage and closes the hold together (never \"oldest matching\", never before the charge is durable): a settled
reservation counts its actual usage and an open one counts its full reserved size, so work in flight is never
free, a call whose usage was never reported stays charged for the day, and no call is ever counted twice.

A refused call raises AdmissionDenied before it reaches the provider and before any charge exists, so quota
refusals keep their 429 path through every LLM helper."""

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nlab.api.limits import limits_of
from nlab.api.settings import Settings
from nlab.db.auth_sessions import utcnow
from nlab.db.errors import LimitReached
from nlab.db.models import BudgetReservation
from nlab.db.storage import admit_write
from nlab.db.usage import Limits, check_counts
from nlab.llm.config import RoleConfig
from nlab.llm.provider import Provider
from nlab.llm.types import AdmissionDenied, Completion, InputTooLarge, Request, Usage

FRAMING_BYTES = 48  # per message: role markers and JSON structure on top of the content bytes
GLOBAL_FRAMING_BYTES = 64  # per request: the chat template the SDK adds around the messages
LEDGER_WRITE_BYTES = 4096  # one provider invocation's budget+ledger rows, against the storage write allowance

_in_flight_total = 0
_in_flight_by_actor: defaultdict[str, int] = defaultdict(int)


class BudgetDenied(AdmissionDenied, LimitReached):
    """The paid call was refused before it started. Both an AdmissionDenied (the LLM layer re-raises it untouched)
    and a LimitReached (the API maps it to 429)."""


class Charge:
    """One billed invocation's reservation. Settlement is exact and durable: one UPDATE on this id writes the
    actual usage and the closure together. `settle(None)` — or usage the provider never reported — keeps the full
    reserved charge for the day."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        id: uuid.UUID,
        role: str,
        model: str,
        reserved_in: int,
        reserved_out: int,
    ) -> None:
        self.id, self._maker, self.role, self.model = id, maker, role, model
        self.reserved_in, self.reserved_out = reserved_in, reserved_out

    async def settle(self, usage: Usage | None = None) -> None:
        if usage is None or not usage.known:
            return  # outcome unknown: the hold is never cleared and keeps counting for the day
        async with self._maker() as db:
            await db.execute(
                update(BudgetReservation)
                .where(BudgetReservation.id == self.id, BudgetReservation.state == "open")
                .values(
                    state="settled",
                    used_in=usage.tokens_in,
                    used_out=usage.tokens_out,
                    closed_at=utcnow(),
                )
            )
            await db.commit()


class Actor:
    """Who pays for the call: the checked caller for interactive work, the session's owner for background work."""

    def __init__(
        self,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        session_id: uuid.UUID | None = None,
        is_guest: bool = False,
    ) -> None:
        self.user_id, self.org_id, self.session_id, self.is_guest = user_id, org_id, session_id, is_guest


def input_bound(request: Request, schema: type[Any] | None = None) -> int:
    """A conservative upper bound of what the call sends as input: a token is never shorter than one UTF-8 byte,
    so raw content bytes are the safe bound (random ASCII, code and Unicode can all reach one token per byte),
    plus the schema JSON the SDK sends alongside and a fixed framing allowance."""
    total = GLOBAL_FRAMING_BYTES
    for message in request.messages:
        total += len(str(message.get("content") or "").encode("utf-8")) + FRAMING_BYTES
    if schema is not None:
        total += len(json.dumps(schema.model_json_schema()).encode("utf-8")) + FRAMING_BYTES
    return total


class Budgeted:
    """The shared provider guard. Wrap the provider once per endpoint or background job with the actor who pays,
    and call complete/stream exactly as before: every invocation admits and reserves its own bounded worst case."""

    def __init__(
        self,
        provider: Provider,
        maker: async_sessionmaker[AsyncSession],
        actor: Actor,
        settings: Callable[[], Settings],
    ) -> None:
        self._provider, self._maker, self._actor, self._settings = provider, maker, actor, settings

    async def complete(
        self, config: RoleConfig, request: Request, schema: type[Any] | None = None, json: bool = False
    ) -> Completion:
        self._check_input(config, request, schema)
        await self._enter()
        try:
            # format fallbacks (json_schema -> json_object -> raw) are physical paid attempts: each resends the
            # input, so the input side covers every attempt; a rejected format request decodes no output
            attempts = 3 if (schema is not None or json) else 1
            charge = await self._insert(
                request.role,
                request.model,
                attempts * input_bound(request, schema),
                _output_bound(config, request),
            )
            async with asyncio.timeout(config.total_deadline_seconds):
                completion = await self._provider.complete(config, request, schema=schema, json=json)
            await charge.settle(completion.usage)  # exact id: unknown usage keeps the full charge
            usage = Usage(
                completion.usage.tokens_in,
                completion.usage.tokens_out,
                completion.usage.known,
                (charge.id,),  # provenance: the caller's ledger row is analytics, excluded from quota sums
            )
            return Completion(completion.text, completion.finish_reason, usage)
        finally:
            self._exit()

    def stream(self, config: RoleConfig, request: Request) -> Any:
        return self._stream(config, request)

    async def _stream(self, config: RoleConfig, request: Request) -> Any:
        self._check_input(config, request, None)
        await self._enter()
        try:
            attempts = 2  # the usage-reporting stream request, and its fallback: both resend the input
            charge = await self._insert(
                request.role, request.model, attempts * input_bound(request), _output_bound(config, request)
            )
            usage = Usage(known=False)  # until the provider reports otherwise, this stream's usage is unknown
            async with asyncio.timeout(config.total_deadline_seconds):
                async for part in self._provider.stream(config, request):
                    if isinstance(part, Usage):
                        usage = part
                        yield Usage(part.tokens_in, part.tokens_out, part.known, (charge.id,))
                    else:
                        yield part
            await charge.settle(usage)  # a stream that reported no usage keeps its full charge
        finally:
            self._exit()

    def charge(self, *, role: str, model: str, input_tokens: int, output_tokens: int) -> Any:
        """The public admission scope for billed work with no chat Request (the native image painter): admits and
        reserves in one short transaction, then yields the exact Charge to settle. Usage the caller never reports
        keeps the full reserved charge."""

        @asynccontextmanager
        async def scope() -> Any:
            await self._enter()
            try:
                yield await self.reserve(role=role, model=model, input_tokens=input_tokens, output_tokens=output_tokens)
            finally:
                self._exit()

        return scope()

    async def reserve(
        self, *, role: str, model: str, input_tokens: int, output_tokens: int, attempts: int = 1
    ) -> Charge:
        return await self._insert(role, model, attempts * input_tokens, attempts * output_tokens)

    async def settle(self, charge: Charge, usage: Usage | None = None) -> None:
        await charge.settle(usage)

    async def _insert(self, role: str, model: str, reserved_in: int, reserved_out: int) -> Charge:
        settings = self._settings()
        async with self._maker() as db:
            await db.execute(text("SELECT pg_advisory_xact_lock(1313620290, 3)"))
            try:
                await check_counts(
                    db,
                    self._limits(),
                    user_id=self._actor.user_id,
                    org_id=self._actor.org_id,
                    is_guest=self._actor.is_guest,
                    extra_tokens=reserved_in + reserved_out,
                    extra_cost=_cost(model, reserved_in, reserved_out, settings),
                )
                if self._actor.user_id is not None and self._actor.org_id is not None:
                    await admit_write(  # bounds budget+ledger row growth, like every other authenticated write
                        db,
                        day=utcnow().date(),
                        user_id=self._actor.user_id,
                        org_id=self._actor.org_id,
                        charged_bytes=LEDGER_WRITE_BYTES,
                        limits=[
                            ("user", settings.limit_user_writes_per_day, settings.limit_user_storage_bytes),
                            ("org", settings.limit_org_writes_per_day, settings.limit_org_storage_bytes),
                            ("global", settings.limit_total_writes_per_day, settings.limit_total_storage_bytes),
                        ],
                    )
            except LimitReached as exc:
                raise BudgetDenied(str(exc)) from exc  # refused before the provider call: no charge is created
            hold = BudgetReservation(
                user_id=self._actor.user_id,
                org_id=self._actor.org_id,
                session_id=self._actor.session_id,
                role=role,
                model=model,
                reserved_in=reserved_in,
                reserved_out=reserved_out,
                state="open",
            )
            db.add(hold)
            await db.commit()
            return Charge(self._maker, hold.id, role, model, reserved_in, reserved_out)

    def _check_input(self, config: RoleConfig, request: Request, schema: type[Any] | None) -> None:
        bound = input_bound(request, schema)
        if bound > config.max_input_tokens:
            raise InputTooLarge(
                f"This request needs about {bound} input tokens; one {request.role} call allows "
                f"{config.max_input_tokens}. Shorten the notes or transcript and try again."
            )

    def _limits(self) -> Limits:
        return limits_of(self._settings())

    async def _enter(self) -> None:
        global _in_flight_total
        limits = self._limits()
        key = str(self._actor.user_id)
        if (limits.max_concurrent_model_calls and _in_flight_total >= limits.max_concurrent_model_calls) or (
            limits.max_concurrent_paid_per_user and _in_flight_by_actor[key] >= limits.max_concurrent_paid_per_user
        ):
            raise BudgetDenied("The service is busy with other practice calls. Try again in a moment.")
        _in_flight_total += 1
        _in_flight_by_actor[key] += 1

    def _exit(self) -> None:
        global _in_flight_total
        key = str(self._actor.user_id)
        _in_flight_total -= 1
        _in_flight_by_actor[key] -= 1
        if _in_flight_by_actor[key] <= 0:
            _in_flight_by_actor.pop(key, None)


def _output_bound(config: RoleConfig, request: Request) -> int:
    return request.max_tokens if request.max_tokens is not None else config.max_output_tokens


def _cost(model: str, reserved_in: int, reserved_out: int, settings: Settings) -> float:
    price_in, price_out = settings.model_prices.get(model, (0.0, 0.0))
    return (reserved_in * price_in + reserved_out * price_out) / 1_000_000
