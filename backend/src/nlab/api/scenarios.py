"""The scenario library: cards, details, create and edit with validation, publishing, covers, brief conversion."""

import base64
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from nlab.api.budget import Actor, Budgeted
from nlab.api.content import Content, Cover
from nlab.api.deps import Db, ViewerDep, content_of, llm_of, settings_of
from nlab.api.limits import limits_of
from nlab.api.pictures import image_mime, paint_step, scene_step
from nlab.api.schemas import (
    BuilderIn,
    BuilderOut,
    ContentIn,
    ConversionOut,
    ConvertIn,
    IssueOut,
    PictureIn,
    PictureOut,
    ScenarioCard,
    ScenarioDetail,
    ScenarioIn,
    StageOut,
    TimingDefaultsOut,
    VisibilityIn,
)
from nlab.db.auth_sessions import utcnow
from nlab.db.errors import Forbidden, LimitReached
from nlab.db.ledger import record_call
from nlab.db.models import LlmCall, Scenario, ScenarioCoverImage
from nlab.db.scenarios import (
    Entry,
    Viewer,
    can_edit,
    can_review,
    copy_of,
    create_scenario,
    delete_scenario,
    get_entry,
    list_scenarios,
    return_scenario,
    set_visibility,
    submit_scenario,
    update_scenario,
    visible_slugs,
    visible_to,
)
from nlab.db.usage import admit, check_limits
from nlab.engine import validate
from nlab.engine.validate import scenario_schema
from nlab.llm import ConversionFailed, convert_upload, phases_of
from nlab.llm.builder import BuilderFailed, build_step
from nlab.llm.types import AdmissionDenied, InputTooLarge

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

MAX_COVER_BYTES = 800 * 1024


def _issues(content: Content, scenario: dict[str, Any]) -> list[IssueOut]:
    return [
        IssueOut(path=issue.path, message=issue.message) for issue in validate(scenario, content.rules, content.rubric)
    ]


def _require_valid(content: Content, scenario: dict[str, Any]) -> None:
    issues = _issues(content, scenario)
    if issues:
        raise HTTPException(422, detail=[issue.model_dump() for issue in issues])


def _card(entry: Entry, viewer: Viewer, cover_version: str | None = None) -> ScenarioCard:
    scenario, content = entry.scenario, entry.version.content
    return ScenarioCard(
        id=scenario.id,
        title=scenario.title,
        cover=Cover(scenario.cover),
        cover_image_version=cover_version,
        visibility=scenario.visibility,
        version=scenario.current_version,
        submitted=scenario.submitted_at is not None,
        difficulty=content.get("difficulty"),
        minutes=content.get("estimated_minutes"),
        skills=list(content.get("skills_tested") or []),
        can_edit=can_edit(scenario, viewer),
    )


def _detail(entry: Entry, viewer: Viewer, cover_version: str | None = None) -> ScenarioDetail:
    card = _card(entry, viewer, cover_version)
    content = entry.version.content
    return ScenarioDetail(
        **card.model_dump(),
        brief=content.get("trainee_brief") or {},
        content=content if card.can_edit or can_review(entry.scenario, viewer) else None,
    )


async def _cover_versions(db: Db, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The custom covers' cache-busters. Only updated_at is read: never the bytes when listing scenarios."""
    if not ids:
        return {}
    rows = await db.execute(
        select(ScenarioCoverImage.scenario_id, ScenarioCoverImage.updated_at).where(
            ScenarioCoverImage.scenario_id.in_(ids)
        )
    )
    return {scenario_id: updated_at.isoformat() for scenario_id, updated_at in rows}


async def readable_cover_versions(db: Db, viewer: Viewer, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Cover cache-busters only for scenarios the viewer can still read: a deleted or hidden scenario's image
    endpoint refuses, so callers (e.g. surviving sessions) must fall back to the theme cover instead."""
    if not ids:
        return {}
    readable = set(await db.scalars(select(Scenario.id).where(Scenario.id.in_(ids), visible_to(viewer))))
    return await _cover_versions(db, sorted(readable))


async def _detail_of(db: Db, entry: Entry, viewer: Viewer) -> ScenarioDetail:
    versions = await _cover_versions(db, [entry.scenario.id])
    return _detail(entry, viewer, versions.get(entry.scenario.id))


@router.get("")
async def library(viewer: ViewerDep, db: Db) -> list[ScenarioCard]:
    entries = await list_scenarios(db, viewer)
    versions = await _cover_versions(db, [entry.scenario.id for entry in entries])
    return [_card(entry, viewer, versions.get(entry.scenario.id)) for entry in entries]


@router.get("/covers")
async def covers() -> list[str]:
    # themes only: a scenario's painted cover is its own tile in the picker
    return [cover.value for cover in Cover if cover is not Cover.custom]


@router.get("/timing-defaults")
async def timing_defaults() -> TimingDefaultsOut:
    return TimingDefaultsOut(
        phases=[
            StageOut(
                id=stage.id,
                label=stage.label,
                hint=stage.hint,
                instruction=stage.instruction,
                allow_injects=stage.allow_injects,
            )
            for stage in phases_of({})
        ],
        warnings=[5, 1],
        silence_after_seconds=90,
    )


@router.get("/schema")
async def schema(request: Request) -> dict[str, Any]:
    return {**scenario_schema(), "x-skills-vocabulary": list(content_of(request).skills_vocabulary)}


@router.post("/validate")
async def check(body: ContentIn, viewer: ViewerDep, request: Request) -> list[IssueOut]:
    return _issues(content_of(request), body.content)


@router.post("/builder")
async def builder_step(body: BuilderIn, viewer: ViewerDep, request: Request, db: Db) -> BuilderOut:
    """One step of the guided builder: the next question (or done). Stateless: the client sends the whole conversation
    each time and saves the scenario itself at the end. The drawing is a separate, optional call."""
    if body.question is None and not body.brief.strip():
        raise HTTPException(422, "Describe your scenario first")
    if body.question is not None and not body.improvise and not (body.answer or "").strip():
        raise HTTPException(422, "Answer the question or ask the AI to improvise")
    provider, config = llm_of(request)
    provider = Budgeted(
        provider,
        request.app.state.sessionmaker,
        Actor(viewer.context.user_id, viewer.context.org_id, is_guest=viewer.context.is_guest),
        lambda: settings_of(request),
    )
    await check_limits(db, limits_of(settings_of(request)), viewer.context)
    try:
        step = await build_step(
            provider,
            config,
            body.brief,
            [{"question": turn.question, "answer": turn.answer} for turn in body.turns],
            body.question,
            body.answer,
            body.improvise,
        )
    except BuilderFailed as exc:
        for record in exc.records:
            record_call(db, record, user_id=viewer.context.user_id, org_id=viewer.context.org_id)
        await db.commit()
        raise HTTPException(502, "The language model did not answer") from exc
    for record in step.records:
        record_call(db, record, user_id=viewer.context.user_id, org_id=viewer.context.org_id)
    await db.commit()
    return BuilderOut(answer=step.answer, question=step.question, done=step.done)


@router.post("/builder/picture")
async def builder_picture(body: PictureIn, viewer: ViewerDep, request: Request, db: Db) -> PictureOut:
    """The painted picture of the scene so far. Decoration: no key or any failure means {image: null}, never a 5xx.
    Each paid stage gets its own limit check: the illustrator's usage is on the ledger before the painter runs."""
    painter = request.app.state.painter
    provider, config = request.app.state.llm
    if not painter.available or config is None:
        return PictureOut(image=None)
    provider = Budgeted(
        provider,
        request.app.state.sessionmaker,
        Actor(viewer.context.user_id, viewer.context.org_id, is_guest=viewer.context.is_guest),
        lambda: settings_of(request),
    )
    previous, previous_mime = None, "image/png"
    if body.previous_image:
        try:
            previous = base64.b64decode(body.previous_image, validate=True)
        except Exception:
            raise HTTPException(422, "The previous image is not valid base64") from None
        if len(previous) > 4 * 1024 * 1024:
            raise HTTPException(422, "The previous image is over 4 MB")
        mime = image_mime(previous)  # before any model call: only real PNG, JPEG or WebP bytes are forwarded
        if mime is None:
            raise HTTPException(422, "The previous image is not a PNG, JPEG or WebP image")
        previous_mime = mime
    await check_limits(db, limits_of(settings_of(request)), viewer.context)
    cap = settings_of(request).limit_user_pictures_per_day
    if cap:  # one atomic admission per picture, before any paid call: off-topic painting stays cheap
        try:
            await admit(db, scope="picture", key=str(viewer.context.user_id), cap=cap, message="Picture limit reached")
        except LimitReached:
            await db.rollback()
            return PictureOut(image=None)  # decoration: the builder carries on without a picture
        await db.commit()
    scene, records = await scene_step(provider, config, body.text)
    for record in records:
        record_call(db, record, user_id=viewer.context.user_id, org_id=viewer.context.org_id)
    await db.commit()  # the paid illustrator usage is visible before the painter's own admission check
    if scene is None:
        return PictureOut(image=None)
    try:
        await check_limits(db, limits_of(settings_of(request)), viewer.context)
    except LimitReached:
        return PictureOut(image=None)  # the illustrator used up the allowance: decoration stops here
    try:
        image, record = await paint_step(painter, scene, previous, previous_mime, body.final, provider)
    except AdmissionDenied:
        return PictureOut(image=None)  # optional painting cannot spend beyond the remaining allowance
    record_call(db, record, user_id=viewer.context.user_id, org_id=viewer.context.org_id)
    await db.commit()
    return PictureOut(image=image)


@router.post("/convert")
async def convert(body: ConvertIn, viewer: ViewerDep, request: Request, db: Db) -> ConversionOut:
    """A draft from a brief. Nothing is saved; the author edits the draft and saves it with POST /api/scenarios."""
    provider, config = llm_of(request)
    provider = Budgeted(
        provider,
        request.app.state.sessionmaker,
        Actor(viewer.context.user_id, viewer.context.org_id, is_guest=viewer.context.is_guest),
        lambda: settings_of(request),
    )
    await check_limits(db, limits_of(settings_of(request)), viewer.context)
    content = content_of(request)
    taken = await visible_slugs(db, viewer)  # before the try: a database error here is not the model's failure
    try:
        result = await convert_upload(
            provider,
            config,
            body.text,
            body.filename,
            taken,
            content.rules,
            content.rubric,
            content.conversion_examples,
            content.skills_vocabulary,
            allow_multiple_counterparts=settings_of(request).allow_multiple_counterparts,
        )
    except (AdmissionDenied, InputTooLarge):
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ConversionFailed as exc:
        for record in exc.records:
            record_call(db, record, user_id=viewer.context.user_id, org_id=viewer.context.org_id)
        await db.commit()
        raise HTTPException(502, "The language model did not answer") from exc
    except Exception as exc:
        # anything unexpected outside the conversion itself: log the failure as one paid row and answer 502
        db.add(
            LlmCall(
                user_id=viewer.context.user_id,
                org_id=viewer.context.org_id,
                role="converter",
                model=config.for_role("converter").model,
                outcome="error",
            )
        )
        await db.commit()
        raise HTTPException(502, "The language model did not answer") from exc
    for record in result.records:
        record_call(db, record, user_id=viewer.context.user_id, org_id=viewer.context.org_id)
    await db.commit()
    return ConversionOut(scenario=result.scenario, errors=result.errors, warnings=result.warnings)


@router.post("", status_code=201)
async def create(body: ScenarioIn, viewer: ViewerDep, request: Request, db: Db) -> ScenarioDetail:
    _require_valid(content_of(request), body.content)
    entry = await create_scenario(db, viewer, body.content, (body.cover or Cover.field).value)
    await db.commit()
    return await _detail_of(db, entry, viewer)


@router.post("/{scenario_id}/duplicate", status_code=201)
async def duplicate(scenario_id: uuid.UUID, viewer: ViewerDep, request: Request, db: Db) -> ScenarioDetail:
    """A private copy for the viewer to edit. Only someone who may read the full content can copy it: a player sees
    the brief alone, and a copy would hand them the hidden parts."""
    source = await get_entry(db, viewer, scenario_id)
    if not (can_edit(source.scenario, viewer) or can_review(source.scenario, viewer)):
        raise Forbidden("You cannot copy this scenario")
    content = copy_of(source.version.content, await visible_slugs(db, viewer))
    _require_valid(content_of(request), content)
    entry = await create_scenario(db, viewer, content, source.scenario.cover)
    if (source_image := await db.get(ScenarioCoverImage, scenario_id)) is not None:  # a copy carries the cover
        db.add(ScenarioCoverImage(scenario_id=entry.scenario.id, data=source_image.data, updated_at=utcnow()))
    await db.commit()
    return await _detail_of(db, entry, viewer)


@router.get("/{scenario_id}")
async def detail(scenario_id: uuid.UUID, viewer: ViewerDep, db: Db) -> ScenarioDetail:
    return await _detail_of(db, await get_entry(db, viewer, scenario_id), viewer)


@router.put("/{scenario_id}")
async def save(scenario_id: uuid.UUID, body: ScenarioIn, viewer: ViewerDep, request: Request, db: Db) -> ScenarioDetail:
    _require_valid(content_of(request), body.content)
    entry = await update_scenario(db, viewer, scenario_id, body.content, body.cover.value if body.cover else None)
    await db.commit()
    return await _detail_of(db, entry, viewer)


@router.put("/{scenario_id}/cover-image", status_code=204)
async def put_cover_image(scenario_id: uuid.UUID, viewer: ViewerDep, request: Request, db: Db) -> None:
    """A custom card cover: WebP bytes, only for someone who may edit the scenario."""
    entry = await get_entry(db, viewer, scenario_id)
    if not can_edit(entry.scenario, viewer):
        raise Forbidden("You cannot edit this scenario")
    if int(request.headers.get("content-length") or 0) > MAX_COVER_BYTES:
        raise HTTPException(413, "The image is over 800 KB")
    chunks = bytearray()
    async for chunk in request.stream():  # a chunked upload stops at the cap instead of buffering everything
        chunks.extend(chunk)
        if len(chunks) > MAX_COVER_BYTES:
            raise HTTPException(413, "The image is over 800 KB")
    data = bytes(chunks)
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise HTTPException(422, "Not a WebP image")
    row = await db.get(ScenarioCoverImage, scenario_id)
    if row is None:
        db.add(ScenarioCoverImage(scenario_id=scenario_id, data=data, updated_at=utcnow()))
    else:
        row.data = data
        row.updated_at = utcnow()
    entry.scenario.cover = Cover.custom.value  # the painting becomes the card's cover; a theme pick can switch back
    await db.commit()


@router.get("/{scenario_id}/cover-image")
async def get_cover_image(scenario_id: uuid.UUID, viewer: ViewerDep, db: Db) -> Response:
    """The custom cover bytes, with the scenario's own visibility (404 otherwise). Cached hard: the URL carries a
    version, and every save of the image changes it."""
    await get_entry(db, viewer, scenario_id)
    row = await db.get(ScenarioCoverImage, scenario_id)
    if row is None:
        raise HTTPException(404, "This scenario has no custom cover")
    return Response(
        row.data,
        media_type="image/webp",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache"},
    )


@router.post("/{scenario_id}/visibility", status_code=204)
async def publish(scenario_id: uuid.UUID, body: VisibilityIn, viewer: ViewerDep, db: Db) -> None:
    await set_visibility(db, viewer, scenario_id, body.visibility)
    await db.commit()


@router.post("/{scenario_id}/submit", status_code=204)
async def submit(scenario_id: uuid.UUID, viewer: ViewerDep, db: Db) -> None:
    await submit_scenario(db, viewer, scenario_id)
    await db.commit()


@router.post("/{scenario_id}/return", status_code=204)
async def hand_back(scenario_id: uuid.UUID, viewer: ViewerDep, db: Db) -> None:
    await return_scenario(db, viewer, scenario_id)
    await db.commit()


@router.delete("/{scenario_id}", status_code=204)
async def remove(scenario_id: uuid.UUID, viewer: ViewerDep, db: Db) -> None:
    await delete_scenario(db, viewer, scenario_id)
    await db.commit()
