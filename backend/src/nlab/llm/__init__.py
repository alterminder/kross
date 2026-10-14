"""Model calls: the model labels, speaks and writes feedback; code checks every quote. No environment access.

The app builds one LLMConfig and one OpenAICompatibleProvider and passes them to the role functions. Every role
returns Result(value, record); the record is a usage-ledger row without user, org and session.
"""

from nlab.llm.agreement import UNCERTAIN_GAP, ScoreCheck, compare_scores
from nlab.llm.answers import Debrief, Evaluation, TurnScores
from nlab.llm.coach import CoachStream, coach_request, coach_scope
from nlab.llm.coach import refusal as coach_refusal
from nlab.llm.config import LLMConfig, RoleConfig, RoleName
from nlab.llm.convert import Conversion, ConversionFailed, convert_brief, convert_upload
from nlab.llm.counterpart import (
    CounterpartStream,
    Phase,
    counterpart_request,
    determine_phase,
    phase_at,
    phases_of,
    render_cue,
)
from nlab.llm.openai_compat import OpenAICompatibleProvider
from nlab.llm.provider import Provider
from nlab.llm.roles import check_bias, classify, debrief, evaluate, grant_check, rewrite_twist
from nlab.llm.types import CallFailed, CallRecord, Line, MalformedAnswer, NoAnswer, Request, Result

__all__ = [
    "CallRecord",
    "CoachStream",
    "Conversion",
    "ConversionFailed",
    "CounterpartStream",
    "Debrief",
    "Evaluation",
    "LLMConfig",
    "Line",
    "MalformedAnswer",
    "CallFailed",
    "NoAnswer",
    "OpenAICompatibleProvider",
    "Phase",
    "Provider",
    "Request",
    "Result",
    "RoleConfig",
    "RoleName",
    "ScoreCheck",
    "TurnScores",
    "UNCERTAIN_GAP",
    "check_bias",
    "classify",
    "compare_scores",
    "coach_refusal",
    "coach_request",
    "coach_scope",
    "convert_brief",
    "convert_upload",
    "counterpart_request",
    "debrief",
    "determine_phase",
    "evaluate",
    "grant_check",
    "phase_at",
    "phases_of",
    "render_cue",
    "rewrite_twist",
]
