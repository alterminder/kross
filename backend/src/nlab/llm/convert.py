"""Brief (markdown or plain text) -> draft scenario. The model maps text onto slots; code owns ids, difficulty,
skills, cultural_profile (always left to ICRC), review and provenance, and rejects the reply unless quoted text is
copied verbatim from the brief and the draft validates. Anything inferred is listed in review.needs_icrc_confirmation.
Nothing is saved here: the author saves the draft."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from nlab.engine import Rubric, Rules, validate
from nlab.engine.conditions import moves_in, parse_condition
from nlab.engine.validate import scenario_schema
from nlab.llm.config import LLMConfig
from nlab.llm.prompts import prompt
from nlab.llm.provider import Provider
from nlab.llm.structured import record_for
from nlab.llm.types import AdmissionDenied, CallRecord, InputTooLarge, Message, Usage, request_for

PROMPT_VERSION = "5"
SKILLS_ERROR = "choose 3 to 5 skills, exactly as written in the list"
SINGLE_COUNTERPART_ERROR = (
    "Generate exactly one counterpart; omit multiparty and interactive stakeholders. "
    "Keep other actors in the situation text and the counterpart's constraints."
)
TBA = "TO BE AUTHORED BY ICRC TRAINER"
LEVELS = ["beginner", "intermediate", "advanced", "expert"]
STOP = {"a", "an", "the", "to", "of", "for", "and", "or", "in", "on", "at"}
HEAD = re.compile(r"^#*\s*SCENARIO\s+(\d+)\s*[—–-]+\s*(.+?)\s*$", re.M)

Chunk = dict[str, Any]  # {"n": bank number or None, "title", "text", "id", "file"?}


class Conversion(BaseModel):
    scenario: dict[str, Any] | None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    attempts: int = 0
    records: list[CallRecord] = Field(default_factory=list)


class ConversionFailed(RuntimeError):
    """The provider failed during a conversion. `records` holds every attempt made, for the usage ledger."""

    def __init__(self, message: str, records: list[CallRecord]) -> None:
        super().__init__(message)
        self.records = records


# ---------- brief -> chunks + facts the code can read without a model -------------------------------------------------


def make_id(n: int | None, title: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOP][:5]
    return (f"s{n:02d}_" if n else "") + ("_".join(words) or "scenario")


def split_bank(text: str) -> list[Chunk]:
    matches = list(HEAD.finditer(text))
    out: list[Chunk] = [
        {
            "n": int(m.group(1)),
            "title": m.group(2).strip('"“” '),
            "text": text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            .split("\n---")[0]
            .strip(),
        }
        for i, m in enumerate(matches)
    ]
    return [{**c, "id": make_id(c["n"], c["title"])} for c in out]


def split(text: str, name: str = "") -> list[Chunk]:
    """Bank format -> one chunk per scenario; any other text -> one chunk titled by its first line."""
    text = text.strip()
    if not text:
        raise ValueError("The file is empty")
    chunks = split_bank(text)
    if chunks:
        return chunks
    first = next((line.strip('# \t"“”') for line in text.splitlines() if line.strip()), "")
    title = first[:80] or name.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "Uploaded brief"
    return [{"n": None, "title": title, "text": text, "id": make_id(None, title), "file": name}]


def section(body: str, name: str) -> str:
    match = re.search(rf"^#{{2,3}}\s*{re.escape(name)}\s*$\n(.*?)(?=^#{{1,3}}\s|\Z)", body, re.M | re.S | re.I)
    return match.group(1) if match else ""


def bullets(body: str, name: str) -> list[str]:
    return [re.sub(r"[;.]$", "", b.strip()) for b in re.findall(r"^\s*-\s+(.*\S)", section(body, name), re.M)]


def facts(c: Chunk) -> dict[str, Any]:
    raw = section(c["text"], "Difficulty").strip()
    found = [d.strip().lower() for d in re.split(r"[/,]", raw) if d.strip().lower() in LEVELS]
    return {
        "difficulty": max(found, key=LEVELS.index) if found else None,
        "difficulty_raw": raw,
        "skills": bullets(c["text"], "Skills Tested"),
        "indicators": bullets(c["text"], "Strong Performance Indicators"),
        "must_clarify": bullets(c["text"], "Trainee Must Clarify"),
        "n_questions": len(re.findall(r'^\s*\d+\.\s+["“]', c["text"], re.M)),
    }


def norm(s: object) -> str:
    return re.sub(r"[\W_]+", " ", str(s).casefold()).strip()


# ---------- prompt ----------------------------------------------------------------------------------------------------


def example_output(s: Mapping[str, Any]) -> str:
    own = {
        k: v for k, v in s.items() if k not in ("schema", "id", "difficulty", "skills_tested", "review", "generated")
    }
    own["sources"] = {"cchn_tools": (s.get("sources") or {}).get("cchn_tools", [])}
    return json.dumps(
        {
            "scenario": own,
            "skills": list(s.get("skills_tested") or []),
            "inferred": (s.get("review") or {}).get("needs_icrc_confirmation", []),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_prompt(
    chunk: Chunk,
    examples: Sequence[Mapping[str, Any]],
    rules: Rules,
    rubric: Rubric,
    vocabulary: Sequence[str] = (),
    *,
    allow_multiple_counterparts: bool = False,
) -> list[Message]:
    moves = "\n".join(f"- {move_id}: {move.description}" for move_id, move in rules.moves.items())
    dims = "\n".join(
        f"- {d}: {cluster.dimensions[d]['label']}" for cluster in rubric.clusters.values() for d in cluster.dimensions
    )
    skills = "".join(f"\n- {skill}" for skill in vocabulary)
    shots = "".join(
        f"\n## Example scenario: {scenario['title']}\n{example_output(scenario)}\n" for scenario in examples
    )
    head = f"SCENARIO {chunk['n']:02d} — {chunk['title']}" if chunk["n"] else chunk["title"]
    schema_json = json.dumps(scenario_schema(), separators=(",", ":"), ensure_ascii=False)
    user = (
        f"# Allowed move ids (only these in `move:`)\n{moves}\n\n# Allowed rubric dimension ids\n{dims}\n"
        + (f"\n# Allowed skills (only these in `skills`, pick 3-5){skills}\n" if vocabulary else "")
        + f"\n# JSON Schema of `scenario`\n{schema_json}\n\n"
        f"# Example outputs (hand-authored scenarios){shots}\n# Convert this brief\n{head}\n{chunk['text']}\n"
    )
    actor_policy = prompt(
        "converter_multiple_counterparts" if allow_multiple_counterparts else "converter_single_counterpart"
    )
    return [
        {"role": "system", "content": prompt("converter_system") + "\n" + actor_policy},
        {"role": "user", "content": user},
    ]


# ---------- code-owned fields + verification -------------------------------------------------------------------


def _pick_skills(chosen: object, vocabulary: Sequence[str]) -> list[str]:
    """The model only selects; code validates: exact matches (case-insensitive) in the vocabulary's spelling,
    deduped, at most 5."""
    canonical = {" ".join(str(skill).split()).casefold(): skill for skill in vocabulary}
    out: list[str] = []
    for item in chosen if isinstance(chosen, list) else []:
        match = canonical.get(" ".join(str(item).split()).casefold())
        if match and match not in out:
            out.append(match)
        if len(out) >= 5:
            break
    return out


def finalize(
    obj: Mapping[str, Any], c: Chunk, fx: dict[str, Any], src_hash: str, model: str, vocabulary: Sequence[str] = ()
) -> dict[str, Any]:
    sc = dict(obj["scenario"])
    picked = [] if fx["skills"] else _pick_skills(obj.get("skills"), vocabulary)
    sc.update(
        schema="negotiation-scenario/v2",
        id=c["id"],
        difficulty=fx["difficulty"] or "intermediate",
        skills_tested=fx["skills"] or picked,
    )
    keep = {k: v for k, v in (sc.get("sources") or {}).items() if k == "cchn_tools"}
    sc["sources"] = (
        {"bank": f"SCENARIO {c['n']:02d}", **keep} if c["n"] else {"file": c.get("file") or "upload", **keep}
    )
    for cp in sc.get("counterparts") or []:
        if isinstance(cp, dict):
            cp["cultural_profile"] = TBA
    inferred = {str(p) for p in obj.get("inferred") or [] if "cultural_profile" not in str(p)} | {
        "counterparts[*].cultural_profile",
        "outcomes",
    }
    if picked:  # the field path once, never the skill labels: the list is a list of paths
        inferred.add("skills_tested")
    notes = []
    if not fx["difficulty"]:
        notes.append("difficulty not stated in the brief -> 'intermediate'")
        inferred.add("difficulty")
    elif "/" in fx["difficulty_raw"]:
        notes.append(f"difficulty range '{fx['difficulty_raw']}' -> '{fx['difficulty']}' (higher end)")
    sc["review"] = {"status": "draft", "needs_icrc_confirmation": sorted(inferred)}
    sc["generated"] = {
        "tool": "nlab.llm.convert",
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "source_sha256": src_hash,
        "notes": notes,
    }
    sc.setdefault("title", c["title"].capitalize())
    return sc


def check(content: dict[str, Any], rules: Rules, rubric: Rubric) -> list[str]:
    """Schema validation (the engine's validate), then cross-references the schema cannot express."""
    errors = [str(issue) for issue in validate(content, rules, rubric)]
    if errors:  # the cross-checks below assume a structurally valid document
        return errors
    for key in ("implementation_checklist", "issues"):
        ids = [item["id"] for item in content.get(key, [])]
        errors += [f"duplicate {key} id '{i}'" for i in set(ids) if ids.count(i) > 1]
    issue_ids = {i["id"] for i in content.get("issues", [])}
    for trigger in content.get("triggers", []):
        p = trigger["when"].get("proposal_reaches")
        if p and p["issue"] not in issue_ids:
            errors.append(f"trigger references unknown issue '{p['issue']}'")
    # the engine validates only the played counterpart; check every raw counterpart's reveal conditions
    for cp in content.get("counterparts", []):
        if not isinstance(cp, dict):
            continue
        for interest in cp.get("hidden_interests", []):
            reveal = interest.get("reveal_when")
            if not reveal:
                continue
            try:
                unknown = moves_in(parse_condition(reveal)) - set(rules.moves)
            except ValueError as exc:
                errors.append(f"invalid reveal_when: {exc}")
                continue
            errors += [f"unknown move '{move}'" for move in sorted(unknown)]
    return errors


def verify(
    sc: dict[str, Any],
    c: Chunk,
    fx: dict[str, Any],
    rules: Rules,
    rubric: Rubric,
    vocabulary: Sequence[str] = (),
    *,
    allow_multiple_counterparts: bool = False,
) -> tuple[list[str], list[str]]:
    errors, warnings = check(sc, rules, rubric), []
    if not allow_multiple_counterparts and (
        not isinstance(sc.get("counterparts"), list)
        or len(sc["counterparts"]) != 1
        or sc.get("stakeholders")
        or "multiparty" in sc
    ):
        errors.insert(0, SINGLE_COUNTERPART_ERROR)
    src = norm(c["text"])

    def quoted(label: str, text: object) -> None:
        if norm(text) not in src:
            errors.append(f"{label} is not copied verbatim from the brief: {str(text)[:90]!r}")

    cps = [cp for cp in sc.get("counterparts", []) if isinstance(cp, dict)]
    for cp in cps:
        who, beh = cp.get("id"), cp.get("behaviours") or {}
        if cp.get("opening"):
            quoted(f"{who}.opening", cp["opening"])
        for q in cp.get("challenges", []):
            quoted(f"{who} challenge", q)
        for q in beh.get("vague_replies", []) + ([beh["closing_test"]] if beh.get("closing_test") else []):
            quoted(f"{who} behaviour line", q)
    for t in sc.get("triggers", []):
        if t.get("say"):
            quoted("trigger.say", t["say"])
    for ph in sc.get("phases", []):
        if ph.get("counterpart_says"):
            quoted(f"phase {ph.get('id')}", ph["counterpart_says"])
    got = sum(len(cp.get("challenges", [])) for cp in cps)
    # A single-counterpart draft omits other speakers' questions from a multi-party brief.
    if allow_multiple_counterparts and fx["n_questions"] and got != fx["n_questions"]:
        errors.append(f"the brief has {fx['n_questions']} numbered questions, the reply has {got} challenges")
    have = [norm(i) for i in (sc.get("rubric") or {}).get("indicators", [])]
    for b in fx["indicators"]:
        if not any(i and (norm(b) in i or i in norm(b)) for i in have):
            errors.append(f"performance indicator missing from rubric.indicators: {b[:90]!r}")
    extra = [i for i in (sc.get("rubric") or {}).get("indicators", []) if norm(i) not in src]
    if extra:
        warnings.append(f"{len(extra)} indicator(s) not taken from the brief")
    if fx["must_clarify"] and len(sc.get("implementation_checklist", [])) != len(fx["must_clarify"]):
        errors.append(
            f"the brief lists {len(fx['must_clarify'])} things to clarify, "
            f"the checklist has {len(sc.get('implementation_checklist', []))}"
        )
    if not any(cp.get("opening") for cp in cps):
        warnings.append("no opening statement in the brief")
    if vocabulary and not fx["skills"] and len(sc.get("skills_tested") or []) < 3:
        errors.append(SKILLS_ERROR)  # the model repairs its choice on the retry
    return errors, warnings


def first_object(raw: str) -> Any:
    """The first JSON object in a reply. Fences, prose before it and text after it are ignored: models with thinking
    on often add a note after the JSON, which used to cost a whole retry."""
    return json.JSONDecoder().raw_decode(raw, raw.index("{"))[0]


async def convert_brief(
    provider: Provider,
    config: LLMConfig,
    chunk: Chunk,
    rules: Rules,
    rubric: Rubric,
    examples: Sequence[Mapping[str, Any]],
    vocabulary: Sequence[str] = (),
    retries: int = 2,
    *,
    allow_multiple_counterparts: bool = False,
) -> Conversion:
    """One brief -> a checked draft. Failed replies get the error list back, `retries` times."""
    role = config.for_role("converter")
    fx = facts(chunk)
    source_hash = hashlib.sha256(chunk["text"].encode()).hexdigest()[:16]
    messages: list[Message] = build_prompt(
        chunk, examples, rules, rubric, vocabulary, allow_multiple_counterparts=allow_multiple_counterparts
    )
    draft: dict[str, Any] | None = None
    errors: list[str] = ["not run"]
    warnings: list[str] = []
    records: list[CallRecord] = []
    for _attempt in range(1, retries + 2):
        request = request_for("converter", role, messages, 0, max_tokens=24000)
        started = time.monotonic()
        try:
            completion = await provider.complete(role, request, json=True)
        except (AdmissionDenied, InputTooLarge):
            raise  # a quota refusal is not a model failure and must keep its 429 path
        except Exception as exc:
            records.append(record_for(request, started, Usage(), "error", 1))
            raise ConversionFailed("The language model did not answer", records) from exc
        raw = completion.text
        try:
            body = first_object(raw)
            draft = finalize(body, chunk, fx, source_hash, role.model, vocabulary)
            errors, warnings = verify(
                draft, chunk, fx, rules, rubric, vocabulary, allow_multiple_counterparts=allow_multiple_counterparts
            )
            if _attempt == retries + 1:  # the last attempt: tags must never sink a conversion
                errors = [error for error in errors if error != SKILLS_ERROR]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            draft, errors, warnings = (
                None,
                [f"the reply is not the expected JSON object ({type(exc).__name__}: {exc})"],
                [],
            )
        if completion.finish_reason == "length":
            errors.append("the reply was cut off; keep it shorter")
        records.append(record_for(request, started, completion.usage, "malformed" if errors else "ok", 1))
        if not errors:
            break
        messages = [
            *messages,
            {"role": "assistant", "content": raw},
            {"role": "user", "content": prompt("converter_fix") + "\n".join("- " + error for error in errors[:12])},
        ]
    if draft and not errors:
        draft["generated"]["warnings"] = warnings
    return Conversion(
        scenario=None if SINGLE_COUNTERPART_ERROR in errors else draft,
        errors=errors,
        warnings=warnings,
        attempts=_attempt,
        records=records,
    )


async def convert_upload(
    provider: Provider,
    config: LLMConfig,
    text: str,
    filename: str,
    taken_ids: Collection[str],
    rules: Rules,
    rubric: Rubric,
    examples: Sequence[Mapping[str, Any]],
    vocabulary: Sequence[str] = (),
    *,
    allow_multiple_counterparts: bool = False,
) -> Conversion:
    """One uploaded brief -> a draft whose id is free among `taken_ids`. Raises ValueError for an empty file or a file
    with several bank scenarios."""
    chunks = split(text, filename)
    if len(chunks) > 1:
        raise ValueError(f"The file holds {len(chunks)} scenarios; upload one at a time")
    chunk = chunks[0]
    base = chunk["id"]
    for number in range(2, 100):
        if chunk["id"] not in taken_ids:
            break
        chunk["id"] = f"{base}_{number}"
    return await convert_brief(
        provider,
        config,
        chunk,
        rules,
        rubric,
        examples,
        vocabulary,
        allow_multiple_counterparts=allow_multiple_counterparts,
    )
