from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import uuid
from typing import TypedDict

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.i18n import (
    FINANCE_CATEGORY_ALIASES,
    RELATIVE_DAY_TERMS,
    TERM_SETS,
    get_planner_examples,
    get_planner_temporal_inheritance_example,
    normalize_locale,
    translate,
    translate_finance_category,
)
from app.crud.finance import create_finance_record, find_recent_duplicate_finance_record, list_finance_records
from app.crud.schedule import create_schedule, list_schedules
from app.crud.team import can_read_team, can_write_team, is_team_member
from app.models.finance import FinanceRecord
from app.models.schedule import Schedule
from app.services.assistant_session_service import (
    clear_session,
    create_session,
    get_session,
    pop_undo_batch,
    save_session,
    save_undo_batch,
)
from app.services import assistant_langgraph
from app.services.llm.openrouter import get_llm_client
from app.services.llm.parser import parse_finance_text, parse_schedule_text

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - fallback when optional dependency is unavailable
    END = START = StateGraph = None


INTENT_CREATE_FINANCE = "create_finance"
INTENT_QUERY_FINANCE = "query_finance"
INTENT_CREATE_SCHEDULE = "create_schedule"
INTENT_QUERY_SCHEDULE = "query_schedule"
INTENT_UNSUPPORTED = "unsupported"

STATUS_COLLECTING = "collecting"
STATUS_EXECUTED = "executed"
STATUS_CANCELLED = "cancelled"
STATUS_UNSUPPORTED = "unsupported"

MAX_PLAN_STEPS = 10
MAX_LOOP_COUNT = 10
GRAPH_SESSION_VERSION = "queue_v3"
SESSION_MODE_CONVERSATION = "conversation"
SESSION_MODE_MUTATION = "mutation"
MAX_CONVERSATION_TURNS = 6
PLANNER_KEYWORD_PREVIEW_LIMIT = 8
MUTATING_INTENTS = {INTENT_CREATE_FINANCE, INTENT_CREATE_SCHEDULE}
ALLOWED_INTENTS = {
    INTENT_CREATE_FINANCE,
    INTENT_QUERY_FINANCE,
    INTENT_CREATE_SCHEDULE,
    INTENT_QUERY_SCHEDULE,
    INTENT_UNSUPPORTED,
}

_BARE_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_MESSAGE_FRAGMENT_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s+")
_ASSISTANT_GRAPH = None
_LANGGRAPH_UNDO_MESSAGE = "__assistant_undo_batch__"
_LANGGRAPH_STAGE_ORDER = (
    "prepare",
    "loop_guard",
    "schedule_subgraph",
    "expense_subgraph",
    "collect_result",
    "commit_batch",
)
_LANGGRAPH_STAGE_MAP = {
    "prepare": "prepare",
    "loop_guard": "loop_guard",
    "dequeue_task": "loop_guard",
    "route_subgraph": "loop_guard",
    "schedule_subgraph": "schedule_subgraph",
    "expense_subgraph": "expense_subgraph",
    "collect_result": "collect_result",
    "commit_batch": "commit_batch",
}


class AssistantGraphState(TypedDict, total=False):
    db: Session | None
    team_id: uuid.UUID | str
    user_id: uuid.UUID | str
    locale: str
    message: str
    session_id: str | None
    incoming_message: str | None
    session_state: dict
    route: str
    step_result: dict
    response: dict


def _assistant_engine() -> str:
    try:
        return str(get_settings().ASSISTANT_ENGINE or "legacy").strip().casefold()
    except Exception:
        return "legacy"


def _use_langgraph_engine() -> bool:
    return _assistant_engine() == "langgraph"


def _langsmith_debug_info() -> dict:
    settings = get_settings()
    return {
        "tracing": bool(settings.LANGSMITH_TRACING),
        "endpoint": settings.LANGSMITH_ENDPOINT,
        "project": settings.LANGSMITH_PROJECT,
        "workspace_id": settings.LANGSMITH_WORKSPACE_ID,
        "api_key_configured": bool(settings.LANGSMITH_API_KEY),
    }


def _apply_langsmith_env_from_settings() -> None:
    settings = get_settings()
    os.environ["LANGSMITH_TRACING"] = "true" if settings.LANGSMITH_TRACING else "false"
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
    if settings.LANGSMITH_WORKSPACE_ID:
        os.environ["LANGSMITH_WORKSPACE_ID"] = settings.LANGSMITH_WORKSPACE_ID


def _normalize_uuid(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _langgraph_assistant_id() -> str:
    return assistant_langgraph.get_assistant_id()


def _new_graph_db_session() -> Session:
    return assistant_langgraph.new_graph_db_session()


def _resolve_langgraph_thread_id(session_id: str | None) -> str:
    return assistant_langgraph.resolve_thread_id(session_id)


def _request_langgraph_json(method: str, path: str, payload: dict | None = None) -> dict:
    return assistant_langgraph.request_json(method, path, payload)


def _post_langgraph_json(path: str, payload: dict) -> dict:
    return assistant_langgraph.post_json(path, payload)


def _get_langgraph_json(path: str) -> dict:
    return assistant_langgraph.get_json(path)


def _ensure_langgraph_thread(*, thread_id: str, team_id: uuid.UUID, user_id: uuid.UUID, locale: str) -> None:
    assistant_langgraph.ensure_thread(thread_id=thread_id, team_id=team_id, user_id=user_id, locale=locale)


def _extract_langgraph_response(payload: dict) -> dict:
    return assistant_langgraph.extract_langgraph_response(payload)


def _collect_langgraph_state_nodes(snapshot: object) -> list[str]:
    return assistant_langgraph.collect_state_nodes(snapshot)


def _map_langgraph_nodes_to_stages(node_names: list[str]) -> list[str]:
    return assistant_langgraph.map_nodes_to_stages(
        node_names,
        stage_map=_LANGGRAPH_STAGE_MAP,
        stage_order=_LANGGRAPH_STAGE_ORDER,
    )


def _normalize_highlighted_stages(stages: list[str]) -> list[str]:
    return assistant_langgraph.normalize_highlighted_stages(stages, stage_order=_LANGGRAPH_STAGE_ORDER)


def _graph_stage_fallback_from_response(response: dict) -> list[str]:
    return assistant_langgraph.graph_stage_fallback_from_response(
        response,
        query_finance_intent=INTENT_QUERY_FINANCE,
        create_finance_intent=INTENT_CREATE_FINANCE,
        query_schedule_intent=INTENT_QUERY_SCHEDULE,
        create_schedule_intent=INTENT_CREATE_SCHEDULE,
        mutating_intents=MUTATING_INTENTS,
        collecting_status=STATUS_COLLECTING,
        executed_status=STATUS_EXECUTED,
        unsupported_status=STATUS_UNSUPPORTED,
        cancelled_status=STATUS_CANCELLED,
        stage_order=_LANGGRAPH_STAGE_ORDER,
    )


def _build_langgraph_visual_state(*, thread_id: str, thread: dict | None, state: dict | None) -> dict:
    return assistant_langgraph.build_visual_state(
        thread_id=thread_id,
        thread=thread,
        state=state,
        stage_map=_LANGGRAPH_STAGE_MAP,
        stage_order=_LANGGRAPH_STAGE_ORDER,
        fallback_stages_fn=_graph_stage_fallback_from_response,
    )


def _get_langgraph_history_states(thread_id: str, *, limit: int = 24) -> list[dict]:
    return assistant_langgraph.get_history_states(thread_id, post_json_fn=_post_langgraph_json, limit=limit)


def _get_langgraph_visual_state(thread_id: str) -> dict:
    return assistant_langgraph.get_visual_state(
        thread_id,
        get_json_fn=_get_langgraph_json,
        post_json_fn=_post_langgraph_json,
        stage_map=_LANGGRAPH_STAGE_MAP,
        stage_order=_LANGGRAPH_STAGE_ORDER,
        fallback_stages_fn=_graph_stage_fallback_from_response,
    )


def _attach_langgraph_visual_state(response: dict, *, thread_id: str) -> dict:
    return assistant_langgraph.attach_visual_state(
        response,
        thread_id=thread_id,
        get_visual_state_fn=_get_langgraph_visual_state,
        fallback_stages_fn=_graph_stage_fallback_from_response,
    )


def get_assistant_graph_state(*, session_id: str | None) -> dict:
    return assistant_langgraph.fetch_graph_state(
        session_id,
        resolve_thread_id_fn=_resolve_langgraph_thread_id,
        get_visual_state_fn=_get_langgraph_visual_state,
    )


def _normalize_text(text: str) -> str:
    return (text or "").strip()


def _contains_any(text: str, terms: set[str]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _equals_any(text: str, terms: set[str]) -> bool:
    lowered = text.casefold()
    return any(lowered == term.casefold() for term in terms)


def _format_amount(value: decimal.Decimal) -> str:
    return format(value.quantize(decimal.Decimal("0.01")), "f")


def _to_decimal(value: float | int | str | decimal.Decimal | None) -> decimal.Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, decimal.Decimal):
        return value.quantize(decimal.Decimal("0.01"))
    return decimal.Decimal(str(value)).quantize(decimal.Decimal("0.01"))


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None




def _format_dt(value: dt.datetime | None, locale: str) -> str:
    if value is None:
        return translate(locale, "assistant.not_set")
    local_value = value.astimezone() if value.tzinfo else value
    return local_value.strftime("%Y-%m-%d %H:%M")


def _finance_category_display(locale: str, category: str) -> str:
    return translate_finance_category(locale, category)


def _normalize_finance_category_value(value: object, locale: str = "zh-CN") -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    normalized = text.casefold()
    mapped = FINANCE_CATEGORY_ALIASES.get(normalized)
    if mapped is None:
        return text
    if mapped == "other":
        return "other"
    return _finance_category_display(locale, mapped)


def _parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _local_now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _day_range(base: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    start = base.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=1)
    return start, end


def _dt_sort_key(value: dt.datetime | None) -> float:
    if value is None:
        return float("inf")
    try:
        normalized = value.astimezone() if value.tzinfo else value.replace(tzinfo=_local_now().tzinfo)
        return normalized.timestamp()
    except Exception:
        return float("inf")


def _build_response(
    *,
    reply: str,
    status: str,
    intent: str | None,
    session_id: str | None,
    missing_slots: list[str] | None = None,
    pending_action: dict | None = None,
    data: dict | None = None,
    cards: list[dict] | None = None,
) -> dict:
    return {
        "reply": reply,
        "status": status,
        "intent": intent,
        "session_id": session_id,
        "missing_slots": missing_slots or [],
        "pending_action": pending_action,
        "data": data,
        "cards": cards or [],
    }


def _response_data(*, can_undo: bool, session_mode: str | None = None, **extra: object) -> dict:
    data = {"can_undo": can_undo}
    if session_mode:
        data["session_mode"] = session_mode
    for key, value in extra.items():
        if value is not None:
            data[key] = value
    return data


def _normalize_session_mode(value: object) -> str:
    text = _normalize_optional_text(value)
    if text == SESSION_MODE_MUTATION:
        return SESSION_MODE_MUTATION
    return SESSION_MODE_CONVERSATION


def _trim_conversation_history(history: list[dict] | None) -> list[dict]:
    items = [dict(item) for item in (history or []) if isinstance(item, dict)]
    if len(items) <= MAX_CONVERSATION_TURNS:
        return items
    return items[-MAX_CONVERSATION_TURNS:]


def _append_conversation_history(
    session_state: dict,
    *,
    user_message: str | None,
    assistant_reply: str,
    intent: str | None,
    status: str,
) -> dict:
    updated = dict(session_state or {})
    history = _trim_conversation_history(updated.get("history") or [])
    history.append(
        {
            "user": _normalize_text(user_message or ""),
            "assistant": _normalize_text(assistant_reply or ""),
            "intent": intent,
            "status": status,
        }
    )
    updated["history"] = _trim_conversation_history(history)
    return updated


def _reset_graph_runtime_state(session_state: dict) -> dict:
    updated = dict(session_state or {})
    updated["tasks"] = []
    updated["current_task"] = None
    updated["loop_count"] = 0
    updated["results"] = []
    updated["reply_parts"] = []
    updated["draft_steps"] = []
    updated["waiting_for_user"] = False
    updated["pending_question"] = None
    updated["missing_slots"] = []
    return updated


def _session_mode_for_steps(steps: list[dict]) -> str:
    if any(isinstance(step, dict) and step.get("intent") in MUTATING_INTENTS for step in steps):
        return SESSION_MODE_MUTATION
    return SESSION_MODE_CONVERSATION


def _term_set_preview(name: str) -> str:
    items = sorted(str(item) for item in TERM_SETS.get(name, set()) if _normalize_optional_text(item))
    if not items:
        return "none"
    return ", ".join(items[:PLANNER_KEYWORD_PREVIEW_LIMIT])


def _planner_examples(locale: str = "zh-CN") -> str:
    return "\n".join(get_planner_examples(locale))


def _planner_history_preview(history: list[dict] | None) -> str:
    items = _trim_conversation_history(history)
    if not items:
        return "none"
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        user_text = _normalize_text(item.get("user") or "")
        intent = _normalize_optional_text(item.get("intent")) or "unknown"
        status = _normalize_optional_text(item.get("status")) or "unknown"
        lines.append(f"{index}. u={user_text or '[empty]'} | i={intent} | s={status}")
    return "\n".join(lines)


def _llm_render_readable_reply(*, locale: str, results: list[dict], fallback_reply: str) -> str:
    client = get_llm_client()
    if not client:
        return fallback_reply
    if not results:
        return fallback_reply
    language_hint = {
        "zh-CN": "Simplified Chinese",
        "en-US": "English",
        "ja-JP": "Japanese",
    }.get(normalize_locale(locale), "Simplified Chinese")
    system = (
        "You rewrite tool results into a user reply.\n"
        f"Reply language: {language_hint}.\n"
        "Use only provided facts.\n"
        "Be concise. No markdown. No extra keys.\n"
        'Return JSON only: {"reply":"..."}'
    )
    user = f"results={results}\nfallback={fallback_reply}"
    try:
        data = client.chat_json(system=system, user=user) or {}
    except Exception:
        return fallback_reply
    reply = _normalize_optional_text(data.get("reply"))
    return reply or fallback_reply


def _serialize_slots(intent: str, slots: dict) -> dict:
    if intent != INTENT_CREATE_SCHEDULE and intent != INTENT_QUERY_SCHEDULE:
        return dict(slots)
    normalized = dict(slots)
    for key in ("start_time", "end_time", "window_start", "window_end"):
        value = normalized.get(key)
        if isinstance(value, dt.datetime):
            normalized[key] = value.isoformat()
    return normalized


def _deserialize_slots(intent: str, slots: dict) -> dict:
    if intent != INTENT_CREATE_SCHEDULE and intent != INTENT_QUERY_SCHEDULE:
        return dict(slots)
    normalized = dict(slots)
    for key in ("start_time", "end_time", "window_start", "window_end"):
        value = normalized.get(key)
        if isinstance(value, str):
            parsed = _parse_iso_datetime(value)
            if parsed:
                normalized[key] = parsed
    return normalized


def _extract_finance_slots(message: str, locale: str) -> dict:
    text = _normalize_text(message)
    # Keep slot extraction deterministic in graph execution.
    parsed = parse_finance_text(text, use_llm=False)
    category = _normalize_finance_category_value(parsed.get("category"), locale)
    if category == "other":
        category = None
    if category is None and _contains_any(text, TERM_SETS["food_terms"]):
        category = _finance_category_display(locale, "food")
    record_type = parsed.get("type")
    has_type_hint = _contains_any(text, TERM_SETS["expense_hints"] | TERM_SETS["income_hints"])
    if parsed.get("type_confidence") == "low":
        record_type = None
    if not has_type_hint and parsed.get("amount") is None:
        record_type = None
    occurred_at = _parse_iso_datetime(parsed.get("occurred_at"))
    note = _normalize_optional_text(parsed.get("note") or text)
    return {
        "amount": parsed.get("amount"),
        "type": record_type,
        "category": category,
        "occurred_at": occurred_at,
        "note": note,
    }


def _extract_schedule_slots(message: str) -> dict:
    text = _normalize_text(message)
    parsed = parse_schedule_text(text)
    title = parsed.get("title")
    if title in (None, "", *TERM_SETS["generic_schedule_titles"]):
        title = None
    return {
        "title": title,
        "start_time": _parse_iso_datetime(parsed.get("start_time")),
        "end_time": _parse_iso_datetime(parsed.get("end_time")),
        "is_all_day": _contains_any(text, TERM_SETS["all_day_hints"]),
    }


def _with_default_schedule_end(slots: dict) -> dict:
    merged = dict(slots or {})
    start_time = merged.get("start_time")
    end_time = merged.get("end_time")
    if start_time and not end_time:
        merged["end_time"] = start_time + dt.timedelta(days=1) if merged.get("is_all_day") else start_time + dt.timedelta(hours=1)
    return merged


def _extract_schedule_query_range(message: str, locale: str) -> tuple[dt.datetime | None, dt.datetime | None, str]:
    text = _normalize_text(message)
    now = _local_now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if _contains_any(text, TERM_SETS["this_month_terms"]):
        next_month = (month_start + dt.timedelta(days=32)).replace(day=1)
        return month_start, next_month, translate(locale, "assistant.query_label_this_month")
    if _contains_any(text, TERM_SETS["last_month_terms"]):
        last_month_end = month_start
        last_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
        return last_month_start, last_month_end, translate(locale, "assistant.query_label_last_month")
    if _contains_any(text, RELATIVE_DAY_TERMS["today"]):
        start, end = _day_range(now)
        return start, end, translate(locale, "assistant.query_label_today")
    if _contains_any(text, RELATIVE_DAY_TERMS["tomorrow"]):
        start, end = _day_range(now + dt.timedelta(days=1))
        return start, end, translate(locale, "assistant.query_label_tomorrow")
    if _contains_any(text, RELATIVE_DAY_TERMS["day_after_tomorrow"]):
        start, end = _day_range(now + dt.timedelta(days=2))
        return start, end, translate(locale, "assistant.query_label_day_after_tomorrow")

    parsed = _extract_schedule_slots(text)
    start_time = parsed.get("start_time")
    if start_time:
        local_start = start_time.astimezone() if start_time.tzinfo else start_time
        start, end = _day_range(local_start)
        return start, end, start.strftime("%Y-%m-%d")
    return None, None, translate(locale, "assistant.query_label_recent")


def _heuristic_intents(message: str) -> list[str]:
    text = _normalize_text(message)
    finance = parse_finance_text(text, use_llm=False)
    schedule = parse_schedule_text(text)
    has_amount = finance.get("amount") is not None
    has_query_hint = _contains_any(text, TERM_SETS["query_hints"])
    has_create_hint = _contains_any(text, TERM_SETS["create_hints"])
    has_finance_hint = _contains_any(text, TERM_SETS["finance_hints"])
    has_explicit_schedule_hint = _contains_any(text, TERM_SETS["schedule_hints"])
    has_schedule_create_hint = _contains_any(text, TERM_SETS["schedule_create_hints"]) or (
        has_create_hint and (has_explicit_schedule_hint or bool(schedule.get("title")) or bool(schedule.get("start_time")))
    )
    has_schedule_time_parse = bool(schedule.get("start_time"))
    is_non_event_schedule = _contains_any(text, TERM_SETS["non_event_schedule_terms"])
    has_schedule_hint = has_explicit_schedule_hint or (
        has_schedule_time_parse and not has_amount and not has_finance_hint and not has_create_hint and not is_non_event_schedule
    )
    has_schedule_query_hint = _contains_any(text, TERM_SETS["schedule_query_hints"])

    intents: list[str] = []
    if has_query_hint and has_finance_hint:
        intents.append(INTENT_QUERY_FINANCE)
    elif has_query_hint and has_schedule_hint and not has_schedule_create_hint:
        intents.append(INTENT_QUERY_SCHEDULE)
    elif has_schedule_query_hint and not has_schedule_create_hint and not has_create_hint:
        intents.append(INTENT_QUERY_SCHEDULE)

    if has_schedule_hint and (has_schedule_create_hint or (not has_query_hint and not has_schedule_query_hint)):
        intents.append(INTENT_CREATE_SCHEDULE)
    if has_amount or has_create_hint or (has_finance_hint and not has_schedule_hint and not has_query_hint):
        intents.append(INTENT_CREATE_FINANCE)

    ordered: list[str] = []
    for intent in intents:
        if intent not in ordered:
            ordered.append(intent)
    return ordered or [INTENT_UNSUPPORTED]


def _sanitize_planned_intents(message: str, intents: list[str]) -> list[str]:
    if not intents:
        return intents
    text = _normalize_text(message)
    finance = parse_finance_text(text, use_llm=False)
    schedule = parse_schedule_text(text)
    has_amount = finance.get("amount") is not None
    has_explicit_schedule_hint = _contains_any(text, TERM_SETS["schedule_hints"]) or _contains_any(text, TERM_SETS["schedule_create_hints"])
    has_finance_hint = (
        _contains_any(text, TERM_SETS["finance_hints"])
        or _contains_any(text, TERM_SETS["expense_hints"])
        or _contains_any(text, TERM_SETS["income_hints"])
        or _contains_any(text, TERM_SETS["food_terms"])
    )
    has_schedule_time = bool(schedule.get("start_time"))
    is_non_event_schedule = _contains_any(text, TERM_SETS["non_event_schedule_terms"])
    has_schedule_hint = has_explicit_schedule_hint or (has_schedule_time and not has_amount and not has_finance_hint and not is_non_event_schedule)
    has_schedule_create_hint = _contains_any(text, TERM_SETS["schedule_create_hints"])
    has_query_hint = _contains_any(text, TERM_SETS["query_hints"]) or _contains_any(text, TERM_SETS["schedule_query_hints"])

    sanitized = [intent for intent in intents if intent in ALLOWED_INTENTS and intent != INTENT_UNSUPPORTED]
    if INTENT_CREATE_SCHEDULE in sanitized and has_amount and has_finance_hint and not has_explicit_schedule_hint:
        sanitized = [intent for intent in sanitized if intent != INTENT_CREATE_SCHEDULE]
    if INTENT_CREATE_SCHEDULE in sanitized and INTENT_CREATE_FINANCE in sanitized:
        if not has_amount and not has_finance_hint:
            sanitized = [intent for intent in sanitized if intent != INTENT_CREATE_FINANCE]
    if INTENT_QUERY_SCHEDULE in sanitized and INTENT_CREATE_SCHEDULE in sanitized:
        if has_query_hint and not has_schedule_create_hint:
            sanitized = [intent for intent in sanitized if intent != INTENT_CREATE_SCHEDULE]
    if INTENT_QUERY_FINANCE in sanitized and INTENT_CREATE_FINANCE in sanitized:
        if has_query_hint and not has_amount:
            sanitized = [intent for intent in sanitized if intent != INTENT_CREATE_FINANCE]
    if INTENT_QUERY_SCHEDULE in sanitized and INTENT_QUERY_FINANCE in sanitized:
        if has_schedule_hint and not has_finance_hint:
            sanitized = [intent for intent in sanitized if intent != INTENT_QUERY_FINANCE]
    if INTENT_CREATE_SCHEDULE in sanitized and is_non_event_schedule and not has_explicit_schedule_hint:
        sanitized = [intent for intent in sanitized if intent != INTENT_CREATE_SCHEDULE]

    ordered: list[str] = []
    for intent in sanitized:
        if intent not in ordered:
            ordered.append(intent)
    return ordered or [INTENT_UNSUPPORTED]


def _plan_intents(message: str, *, history: list[dict] | None = None, locale: str = "zh-CN") -> tuple[list[str], bool]:
    text = _normalize_text(message)
    fallback = _heuristic_intents(text)
    if fallback == [INTENT_UNSUPPORTED]:
        fallback = []

    client = get_llm_client()
    if not client:
        return (fallback or [INTENT_UNSUPPORTED], False)

    sysdate = _local_now().strftime("%Y-%m-%d %H:%M:%S %z")
    system = (
        "You are a classifier for a team assistant.\n"
        f"Now={sysdate}\n"
        "Choose only from: create_finance, query_finance, create_schedule, query_schedule.\n"
        "Return ordered steps only. Max 5 steps.\n"
        "query_* means asking about existing data.\n"
        "create_* means asking to record or update data.\n"
        "Schedule/activity/rehearsal/meeting/performance/time/place => schedule.\n"
        "Money/income/expense/reimbursement/budget/profit => finance.\n"
        "If the message is just greeting/small talk, return steps=[].\n"
        "If it truly needs more than 5 actions, set need_split=true.\n"
        f"Examples:\n{_planner_examples(locale)}\n"
        'JSON schema: {"steps":[{"intent":"create_finance|query_finance|create_schedule|query_schedule"}],"need_split":false}'
    )
    user = (
        f"history:\n{_planner_history_preview(history)}\n"
        f"message:\n{text}"
    )
    try:
        data = client.chat_json(system=system, user=user, max_tokens=120, allow_auto_switch=False) or {}
    except Exception:
        return (fallback or [INTENT_UNSUPPORTED], False)

    if bool(data.get("need_split")):
        return ([], True)
    raw_steps = data.get("steps") or []
    intents: list[str] = []
    if isinstance(raw_steps, list):
        for item in raw_steps:
            intent = item.get("intent") if isinstance(item, dict) else item
            if intent in ALLOWED_INTENTS and intent not in intents and intent != INTENT_UNSUPPORTED:
                intents.append(intent)
    intents = _sanitize_planned_intents(text, intents)
    if len(intents) > MAX_PLAN_STEPS:
        return ([], True)
    if intents:
        return (intents, False)
    return (fallback or [INTENT_UNSUPPORTED], False)


def _normalize_planned_amount(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_planned_datetime(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    text = _normalize_optional_text(value)
    if not text:
        return None
    return _parse_iso_datetime(text)


def _planned_slots_from_item(intent: str, item: dict, source_text: str, locale: str) -> dict:
    if intent == INTENT_CREATE_FINANCE:
        category = _normalize_finance_category_value(item.get("category"), locale)
        return {
            "amount": _normalize_planned_amount(item.get("amount")),
            "type": _normalize_optional_text(item.get("type")),
            "category": None if category == "other" else category,
            "occurred_at": _normalize_planned_datetime(item.get("occurred_at")),
            "note": _normalize_optional_text(item.get("note")) or source_text,
        }
    if intent == INTENT_CREATE_SCHEDULE:
        return {
            "title": _normalize_optional_text(item.get("title")),
            "start_time": _normalize_planned_datetime(item.get("start_time")),
            "end_time": _normalize_planned_datetime(item.get("end_time")),
            "is_all_day": bool(item.get("is_all_day")),
        }
    if intent == INTENT_QUERY_FINANCE:
        return {
            "question": _normalize_optional_text(item.get("question")) or source_text,
            "window_start": _normalize_planned_datetime(item.get("window_start")),
            "window_end": _normalize_planned_datetime(item.get("window_end")),
            "label": _normalize_optional_text(item.get("label")),
        }
    if intent == INTENT_QUERY_SCHEDULE:
        return {
            "window_start": _normalize_planned_datetime(item.get("window_start")),
            "window_end": _normalize_planned_datetime(item.get("window_end")),
            "label": _normalize_optional_text(item.get("label")),
        }
    return {}


def _sanitize_planned_step_items(message: str, raw_steps: list[object], locale: str) -> list[dict]:
    sanitized_steps: list[dict] = []
    full_message = _normalize_text(message)
    for item in raw_steps:
        if isinstance(item, dict):
            intent = item.get("intent")
            source_text = _normalize_optional_text(item.get("source_text")) or full_message
        else:
            intent = item
            source_text = full_message
        sanitized_intents = _sanitize_planned_intents(source_text, [intent] if intent else [])
        if not sanitized_intents or sanitized_intents == [INTENT_UNSUPPORTED]:
            continue
        resolved_intent = sanitized_intents[0]
        step_payload = {"intent": resolved_intent, "source_text": source_text or full_message}
        if isinstance(item, dict):
            step_payload["slots"] = _planned_slots_from_item(resolved_intent, item, source_text or full_message, locale)
        sanitized_steps.append(step_payload)
    return sanitized_steps


def _plan_step_items(message: str, *, history: list[dict] | None = None, locale: str = "zh-CN") -> tuple[list[dict], bool]:
    text = _normalize_text(message)
    if not text:
        return [], False

    client = get_llm_client()
    if not client:
        return [], False

    sysdate = _local_now().strftime("%Y-%m-%d %H:%M:%S %z")
    system = (
        "You are a task planner for a team assistant.\n"
        f"Now={sysdate}\n"
        "Split the user message into ordered actionable items and extract structured fields.\n"
        "Infer item boundaries even when punctuation is missing, informal, or ASR-style.\n"
        "Each item must map to exactly one intent from: create_finance, query_finance, create_schedule, query_schedule.\n"
        "Keep source_text short and specific to that item, in the user's original language.\n"
        "For finance items, extract amount, type, category, occurred_at, and note.\n"
        "For schedule items, extract title, start_time, end_time, and is_all_day when applicable.\n"
        "For query items, extract label and date window if explicit.\n"
        "If a later item omits time/date but clearly shares temporal context with a previous item, inherit that temporal context.\n"
        f"{get_planner_temporal_inheritance_example(locale)}"
        "Set note to the original wording of that item, not a rewritten summary.\n"
        "Datetime fields must be ISO8601 with timezone when you can infer them reliably.\n"
        "Do not merge separate finance or schedule items into one step.\n"
        "If the message is just greeting/small talk, return steps=[].\n"
        f"If it truly needs more than {MAX_PLAN_STEPS} actions, set need_split=true.\n"
        f"Examples:\n{_planner_examples(locale)}\n"
        'JSON schema: {"steps":[{"intent":"create_finance|query_finance|create_schedule|query_schedule","source_text":"...","amount":number|null,"type":"income|expense|null","category":string|null,"occurred_at":"ISO8601|null","note":string|null,"title":string|null,"start_time":"ISO8601|null","end_time":"ISO8601|null","is_all_day":boolean|null,"question":string|null,"window_start":"ISO8601|null","window_end":"ISO8601|null","label":string|null}],"need_split":false}'
    )
    user = (
        f"history:\n{_planner_history_preview(history)}\n"
        f"message:\n{text}"
    )
    try:
        data = client.chat_json(system=system, user=user, max_tokens=700, allow_auto_switch=False) or {}
    except Exception:
        return [], False

    if bool(data.get("need_split")):
        return [], True
    raw_steps = data.get("steps") or []
    if not isinstance(raw_steps, list):
        return [], False

    items = _sanitize_planned_step_items(text, raw_steps, locale)
    if len(items) > MAX_PLAN_STEPS:
        return [], True
    if len(items) > 1 and {item.get("source_text") for item in items} == {text}:
        return [], False
    return items, False


def _required_slots(intent: str) -> list[str]:
    if intent == INTENT_CREATE_FINANCE:
        return ["amount", "type"]
    if intent == INTENT_CREATE_SCHEDULE:
        return ["title", "start_time", "end_time"]
    return []


def _slot_prompt(intent: str, slot_name: str, locale: str) -> str:
    prompt_map = {
        INTENT_CREATE_FINANCE: {
            "amount": "assistant.slot_finance_amount",
            "type": "assistant.slot_finance_type",
            "category": "assistant.slot_finance_category",
        },
        INTENT_CREATE_SCHEDULE: {
            "title": "assistant.slot_schedule_title",
            "start_time": "assistant.slot_schedule_start_time",
            "end_time": "assistant.slot_schedule_end_time",
        },
    }
    key = prompt_map.get(intent, {}).get(slot_name, "assistant.slot_fallback")
    return translate(locale, key)


def _slot_prompt_with_context(intent: str, slot_name: str, locale: str, source_text: str | None) -> str:
    question = _slot_prompt(intent, slot_name, locale)
    source = _normalize_text(source_text or "")
    if not source:
        return question
    return translate(locale, "assistant.slot_with_context", source=source, question=question)


def _extract_slots_for_intent(intent: str, message: str, locale: str, current_slots: dict | None = None) -> dict:
    base: dict = {}
    if intent == INTENT_CREATE_FINANCE:
        base = _extract_finance_slots(message, locale)
        if base.get("amount") in (None, ""):
            match = _BARE_NUMBER_RE.search(_normalize_text(message))
            if match:
                try:
                    base["amount"] = float(match.group(0))
                except Exception:
                    pass
    elif intent == INTENT_CREATE_SCHEDULE:
        base = _with_default_schedule_end(_extract_schedule_slots(message))
    elif intent == INTENT_QUERY_SCHEDULE:
        start, end, label = _extract_schedule_query_range(message, locale)
        base = {"window_start": start, "window_end": end, "label": label}
    elif intent == INTENT_QUERY_FINANCE:
        text = _normalize_text(message)
        base = {"question": text} if text else {}
        start, end, label = _extract_schedule_query_range(message, locale)
        if start is not None and end is not None:
            base["window_start"] = start
            base["window_end"] = end
            base["label"] = label

    # Slot extraction is deterministic by design; only prepare uses LLM for intent planning.
    return dict(base)


def _merge_slots(intent: str, current_slots: dict, incoming_slots: dict) -> dict:
    merged = dict(current_slots or {})
    for key, value in (incoming_slots or {}).items():
        if value not in (None, ""):
            if intent == INTENT_CREATE_FINANCE and key == "note" and merged.get("note") not in (None, ""):
                continue
            merged[key] = value
    return _with_default_schedule_end(merged) if intent == INTENT_CREATE_SCHEDULE else merged


def _has_explicit_temporal_hint(text: str) -> bool:
    pattern = (
        r"(今|明|后|昨|前)天|这周|本周|下周|下下周|周[一二三四五六日天末]|星期[一二三四五六日天]|"
        r"\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,2})?|(?:\d{1,4}年)?\d{1,2}月\d{1,2}[日号]?|"
        r"上午|下午|晚上|中午|凌晨|\d{1,2}点(?:半|\d{1,2}分)?"
    )
    return bool(re.search(pattern, _normalize_text(text)))


def _propagate_adjacent_temporal_context(steps: list[dict]) -> list[dict]:
    propagated: list[dict] = []
    previous_finance_occurred_at: dt.datetime | None = None
    for step in steps:
        current = dict(step)
        intent = current.get("intent")
        slots = _deserialize_slots(intent, current.get("slots", {}))
        source_text = _normalize_text(current.get("source_text") or "")

        if intent == INTENT_CREATE_FINANCE:
            if previous_finance_occurred_at is not None and not _has_explicit_temporal_hint(source_text):
                slots["occurred_at"] = previous_finance_occurred_at
            if isinstance(slots.get("occurred_at"), dt.datetime):
                previous_finance_occurred_at = slots["occurred_at"]
        else:
            previous_finance_occurred_at = None

        current["slots"] = _serialize_slots(intent, slots)
        propagated.append(current)
    return propagated


def _missing_slots(intent: str, slots: dict) -> list[str]:
    missing: list[str] = []
    for key in _required_slots(intent):
        if slots.get(key) in (None, ""):
            missing.append(key)
    return missing


def _build_step_summary(step: dict, locale: str) -> str:
    intent = step["intent"]
    slots = _deserialize_slots(intent, step.get("slots", {}))
    if intent == INTENT_CREATE_FINANCE:
        amount = _format_amount(_to_decimal(slots.get("amount")) or decimal.Decimal("0"))
        record_type = translate(locale, f"assistant.record_type_{slots.get('type') or 'expense'}")
        category = slots.get("category") or translate(locale, "assistant.not_categorized")
        return translate(locale, "assistant.plan_step_create_finance", record_type=record_type, category=category, amount=amount)
    if intent == INTENT_CREATE_SCHEDULE:
        return translate(
            locale,
            "assistant.plan_step_create_schedule",
            title=slots.get("title") or translate(locale, "assistant.not_set"),
            start=_format_dt(slots.get("start_time"), locale),
            end=_format_dt(slots.get("end_time"), locale),
        )
    if intent == INTENT_QUERY_SCHEDULE:
        return translate(locale, "assistant.plan_step_query_schedule", label=slots.get("label") or translate(locale, "assistant.query_label_recent"))
    if intent == INTENT_QUERY_FINANCE:
        return translate(locale, "assistant.plan_step_query_finance", question=slots.get("question") or translate(locale, "assistant.not_set"))
    return intent


def _build_confirmation_reply(steps: list[dict], locale: str) -> str:
    lines = [translate(locale, "assistant.batch_plan_header")]
    for idx, step in enumerate(steps, start=1):
        lines.append(f"{idx}. {_build_step_summary(step, locale)}")
    lines.append(translate(locale, "assistant.batch_confirm_hint"))
    return "\n".join(lines)


def _split_composite_fragment(fragment: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[，,、]+", fragment) if part and part.strip()]
    if len(parts) <= 1:
        return [fragment]
    if all(_heuristic_intents(part) != [INTENT_UNSUPPORTED] for part in parts):
        return parts
    return [fragment]


def _split_message_fragments(message: str) -> list[str]:
    text = _normalize_text(message).replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return []
    fragments: list[str] = []
    for line in text.split("\n"):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        parts = re.split(r"[。！？!?；;]+\s*", stripped_line)
        for part in parts:
            fragment = part.strip()
            if fragment:
                fragments.extend(_split_composite_fragment(fragment))
    return fragments


def _make_initial_steps(intents: list[str], message: str, locale: str, *, source_text: str | None = None) -> list[dict]:
    steps: list[dict] = []
    source = _normalize_text(source_text or message)
    for intent in intents:
        if intent not in ALLOWED_INTENTS or intent == INTENT_UNSUPPORTED:
            continue
        slots = _extract_slots_for_intent(intent, source or message, locale, current_slots=None)
        steps.append({"intent": intent, "slots": _serialize_slots(intent, slots), "source_text": source or message})
    return steps


def _plan_steps_from_text(message: str, *, locale: str, history: list[dict] | None = None) -> tuple[list[dict] | None, dict | None]:
    planned_items, need_split = _plan_step_items(message, history=history, locale=locale)
    if need_split:
        return None, _build_response(
            reply=translate(locale, "assistant.too_many_steps", count=MAX_PLAN_STEPS),
            status=STATUS_UNSUPPORTED,
            intent=INTENT_UNSUPPORTED,
            session_id=None,
            data=_response_data(can_undo=False),
        )
    if planned_items:
        steps: list[dict] = []
        for item in planned_items:
            intent = item["intent"]
            source_text = item.get("source_text") or message
            extracted_slots = _extract_slots_for_intent(intent, source_text, locale, current_slots=None)
            llm_slots = dict(item.get("slots") or {})
            merged_slots = _merge_slots(intent, extracted_slots, llm_slots)
            steps.append({
                "intent": intent,
                "slots": _serialize_slots(intent, merged_slots),
                "source_text": source_text,
            })
        steps = _propagate_adjacent_temporal_context(steps)
        return steps, None

    intents, need_split = _plan_intents(message, history=history, locale=locale)
    if need_split:
        return None, _build_response(
            reply=translate(locale, "assistant.too_many_steps", count=MAX_PLAN_STEPS),
            status=STATUS_UNSUPPORTED,
            intent=INTENT_UNSUPPORTED,
            session_id=None,
            data=_response_data(can_undo=False),
        )
    steps = _make_initial_steps(intents, message, locale, source_text=message)
    return steps, None


def _plan_graph_steps(message: str, *, locale: str, history: list[dict] | None = None) -> tuple[list[dict] | None, dict | None]:
    fragments = _split_message_fragments(message)
    steps: list[dict] = []
    if len(fragments) > 1:
        for fragment in fragments:
            fragment_steps, response = _plan_steps_from_text(fragment, locale=locale, history=None)
            if response is not None:
                if response.get("intent") == INTENT_UNSUPPORTED and response.get("status") == STATUS_UNSUPPORTED:
                    continue
                return None, response
            steps.extend(fragment_steps or [])
    else:
        planned_steps, response = _plan_steps_from_text(message, locale=locale, history=history)
        if response is not None:
            return None, response
        steps = planned_steps or []

    steps = _propagate_adjacent_temporal_context(steps)
    if not steps:
        return None, _build_response(
            reply=translate(locale, "assistant.unsupported"),
            status=STATUS_UNSUPPORTED,
            intent=INTENT_UNSUPPORTED,
            session_id=None,
            data=_response_data(can_undo=False),
        )
    if len(steps) > MAX_PLAN_STEPS:
        return None, _build_response(
            reply=translate(locale, "assistant.too_many_steps", count=len(steps)),
            status=STATUS_UNSUPPORTED,
            intent=INTENT_UNSUPPORTED,
            session_id=None,
            data=_response_data(can_undo=False),
        )
    return steps, None


def _find_next_incomplete_step(steps: list[dict], start_index: int = 0) -> tuple[int, list[str]]:
    idx = max(0, start_index)
    while idx < len(steps):
        step = steps[idx]
        missing = _missing_slots(step["intent"], _deserialize_slots(step["intent"], step.get("slots", {})))
        if missing:
            return idx, missing
        idx += 1
    return len(steps), []


def _has_mutating_step(steps: list[dict]) -> bool:
    return any(step.get("intent") in MUTATING_INTENTS for step in steps)


def message_requires_write_access(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    locale: str,
) -> bool:
    if not can_read_team(db, team_id=team_id, user_id=user_id):
        return False
    if can_write_team(db, team_id=team_id, user_id=user_id):
        return False
    if message == _LANGGRAPH_UNDO_MESSAGE:
        return True
    planned_steps, response = _plan_graph_steps(message, locale=normalize_locale(locale))
    if response is not None or not planned_steps:
        return False
    return _has_mutating_step(planned_steps)


def _query_schedule(
    db: Session,
    *,
    team_id: uuid.UUID,
    window_start: dt.datetime | None,
    window_end: dt.datetime | None,
    label: str,
    locale: str,
) -> dict:
    items = list_schedules(db, team_id=team_id)
    if window_start and window_end:
        matched: list[Schedule] = []
        for item in items:
            item_start = item.start_time
            if not item_start:
                continue
            compare_start = item_start.astimezone() if item_start.tzinfo else item_start.replace(tzinfo=window_start.tzinfo)
            if window_start <= compare_start < window_end:
                matched.append(item)
        matched.sort(key=lambda item: _dt_sort_key(item.start_time))
    else:
        now = _local_now()
        matched = []
        for item in items:
            item_start = item.start_time
            if not item_start:
                continue
            compare_start = item_start.astimezone() if item_start.tzinfo else item_start.replace(tzinfo=now.tzinfo)
            if compare_start >= now:
                matched.append(item)
        matched.sort(key=lambda item: _dt_sort_key(item.start_time))
        matched = matched[:5]

    if not matched:
        return {"reply": translate(locale, "assistant.query_schedule_empty", label=label), "data": {"items": [], "label": label}}

    lines = [translate(locale, "assistant.query_schedule_count", label=label, count=len(matched))]
    data_items = []
    for item in matched[:5]:
        line = translate(
            locale,
            "assistant.query_schedule_line_with_end" if item.end_time else "assistant.query_schedule_line",
            title=item.title,
            start=_format_dt(item.start_time, locale),
            end=_format_dt(item.end_time, locale),
        )
        if item.location:
            line = translate(locale, "assistant.query_schedule_line_with_location", line=line, location=item.location)
        lines.append(line)
        data_items.append(
            {
                "id": str(item.id),
                "title": item.title,
                "start_time": item.start_time.isoformat() if item.start_time else None,
                "end_time": item.end_time.isoformat() if item.end_time else None,
                "location": item.location,
                "status": item.status,
            }
        )
    return {"reply": "\n".join(lines), "data": {"items": data_items, "label": label}}


def _query_finance(
    db: Session,
    *,
    team_id: uuid.UUID,
    question: str,
    locale: str,
    window_start: dt.datetime | None,
    window_end: dt.datetime | None,
) -> dict:
    text = _normalize_text(question)
    records = list_finance_records(
        db,
        team_id=team_id,
        window_start=window_start,
        window_end=window_end,
    )
    if not records:
        return {"reply": translate(locale, "finance.no_result"), "data": {"items": [], "expense_total": "0.00", "income_total": "0.00"}}

    ask_last_month_food = _contains_any(text, TERM_SETS["last_month_terms"]) and (
        _contains_any(text, TERM_SETS["food_terms"]) or _contains_any(text, TERM_SETS["food_categories"])
    )
    if ask_last_month_food:
        now = _local_now()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = this_month_start
        last_month_start = (this_month_start - dt.timedelta(days=1)).replace(day=1)
        food_categories = {term.casefold() for term in TERM_SETS["food_categories"]}
        filtered = []
        for item in records:
            occurred_at = item.occurred_at
            if not occurred_at:
                continue
            compared = occurred_at.astimezone() if occurred_at.tzinfo else occurred_at.replace(tzinfo=now.tzinfo)
            category = (item.category or "").casefold()
            if last_month_start <= compared < last_month_end and category in food_categories:
                filtered.append(item)
        total = sum((item.amount for item in filtered), decimal.Decimal("0.00"))
        return {
            "reply": translate(locale, "finance.last_month_food", total=_format_amount(total)),
            "data": {"items": [str(item.id) for item in filtered], "expense_total": _format_amount(total), "income_total": "0.00"},
        }

    expense_total = decimal.Decimal("0.00")
    income_total = decimal.Decimal("0.00")
    for item in records:
        if item.type == "expense":
            expense_total += item.amount
        elif item.type == "income":
            income_total += item.amount
    return {
        "reply": translate(locale, "finance.total_expense", total=_format_amount(expense_total)),
        "data": {
            "items": [str(item.id) for item in records],
            "expense_total": _format_amount(expense_total),
            "income_total": _format_amount(income_total),
            "count": len(records),
        },
    }


def _execute_step(db: Session, *, step: dict, team_id: uuid.UUID, user_id: uuid.UUID, locale: str) -> dict:
    intent = step["intent"]
    slots = _deserialize_slots(intent, step.get("slots", {}))
    if intent == INTENT_QUERY_FINANCE:
        result = _query_finance(
            db,
            team_id=team_id,
            question=slots.get("question") or "",
            locale=locale,
            window_start=slots.get("window_start"),
            window_end=slots.get("window_end"),
        )
        return {"status": STATUS_EXECUTED, "intent": intent, "reply": result.get("reply", ""), "data": result.get("data")}

    if intent == INTENT_QUERY_SCHEDULE:
        result = _query_schedule(
            db,
            team_id=team_id,
            window_start=slots.get("window_start"),
            window_end=slots.get("window_end"),
            label=slots.get("label") or translate(locale, "assistant.query_label_recent"),
            locale=locale,
        )
        return {"status": STATUS_EXECUTED, "intent": intent, "reply": result["reply"], "data": result["data"]}

    if intent == INTENT_CREATE_FINANCE:
        amount = _to_decimal(slots.get("amount"))
        if amount is None:
            return {"status": STATUS_UNSUPPORTED, "intent": intent, "reply": translate(locale, "assistant.slot_finance_amount"), "data": None}
        occurred_at = slots.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = _parse_iso_datetime(occurred_at)
        category = _normalize_optional_text(slots.get("category")) or translate(locale, "assistant.not_categorized")
        resolved_occurred_at = occurred_at or dt.datetime.now(dt.timezone.utc)
        resolved_location = _normalize_optional_text(slots.get("location"))
        resolved_note = _normalize_optional_text(slots.get("note"))
        duplicate = find_recent_duplicate_finance_record(
            db,
            team_id=team_id,
            user_id=user_id,
            amount=amount,
            record_type=slots["type"],
            category=category,
            occurred_at=resolved_occurred_at,
            location=resolved_location,
            note=resolved_note,
        )
        if duplicate:
            return {
                "status": STATUS_EXECUTED,
                "intent": intent,
                "reply": translate(
                    locale,
                    "assistant.created_finance",
                    record_type=translate(locale, f"assistant.record_type_{duplicate.type}"),
                    category=duplicate.category,
                    amount=_format_amount(duplicate.amount),
                ),
                "data": {
                    "record_id": str(duplicate.id),
                    "amount": _format_amount(duplicate.amount),
                    "type": duplicate.type,
                    "category": duplicate.category,
                    "occurred_at": duplicate.occurred_at.isoformat() if getattr(duplicate, "occurred_at", None) else None,
                    "location": duplicate.location,
                    "note": duplicate.note,
                    "deduplicated": True,
                },
            }
        record = create_finance_record(
            db,
            team_id=team_id,
            user_id=user_id,
            amount=amount,
            record_type=slots["type"],
            category=category,
            occurred_at=resolved_occurred_at,
            location=resolved_location,
            location_latitude=None,
            location_longitude=None,
            note=resolved_note,
        )
        return {
            "status": STATUS_EXECUTED,
            "intent": intent,
            "reply": translate(
                locale,
                "assistant.created_finance",
                record_type=translate(locale, f"assistant.record_type_{record.type}"),
                category=record.category,
                amount=_format_amount(record.amount),
            ),
            "data": {
                "record_id": str(record.id),
                "amount": _format_amount(record.amount),
                "type": record.type,
                "category": record.category,
                "occurred_at": record.occurred_at.isoformat() if getattr(record, "occurred_at", None) else None,
                "location": record.location,
                "note": record.note,
            },
            "undo": {"intent": INTENT_CREATE_FINANCE, "record_id": str(record.id)},
        }

    if intent == INTENT_CREATE_SCHEDULE:
        start_time = slots.get("start_time")
        end_time = slots.get("end_time")
        if not start_time or not end_time:
            return {"status": STATUS_UNSUPPORTED, "intent": intent, "reply": translate(locale, "assistant.slot_schedule_start_time"), "data": None}
        item = create_schedule(
            db,
            team_id=team_id,
            title=slots["title"],
            description=_normalize_optional_text(slots.get("description")),
            location=_normalize_optional_text(slots.get("location")),
            location_latitude=None,
            location_longitude=None,
            is_all_day=bool(slots.get("is_all_day")),
            start_time=start_time,
            end_time=end_time,
            created_by=user_id,
        )
        return {
            "status": STATUS_EXECUTED,
            "intent": intent,
            "reply": translate(locale, "assistant.created_schedule", title=item.title, start=_format_dt(item.start_time, locale), end=_format_dt(item.end_time, locale)),
            "data": {
                "schedule_id": str(item.id),
                "title": item.title,
                "start_time": item.start_time.isoformat() if item.start_time else None,
                "end_time": item.end_time.isoformat() if item.end_time else None,
                "location": item.location,
                "description": item.description,
                "is_all_day": item.is_all_day,
            },
            "undo": {"intent": INTENT_CREATE_SCHEDULE, "record_id": str(item.id)},
        }

    return {"status": STATUS_UNSUPPORTED, "intent": INTENT_UNSUPPORTED, "reply": translate(locale, "assistant.unsupported"), "data": None}


def _save_undo_batch(team_id: uuid.UUID, user_id: uuid.UUID, actions: list[dict]) -> None:
    save_undo_batch(team_id, user_id, actions)


def _execute_planned_steps(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, steps: list[dict], locale: str) -> dict:
    replies: list[str] = []
    results: list[dict] = []
    undo_actions: list[dict] = []
    for step in steps:
        result = _execute_step(db, step=step, team_id=team_id, user_id=user_id, locale=locale)
        if result.get("reply"):
            replies.append(result["reply"])
        results.append({"intent": result.get("intent"), "status": result.get("status"), "data": result.get("data")})
        if result.get("undo"):
            undo_actions.append(result["undo"])
        if result.get("status") != STATUS_EXECUTED:
            return _build_response(reply="\n\n".join(replies), status=STATUS_UNSUPPORTED, intent=result.get("intent"), session_id=None, data={"results": results, "can_undo": False})
    _save_undo_batch(team_id, user_id, undo_actions)
    return _build_response(
        reply="\n\n".join(replies),
        status=STATUS_EXECUTED,
        intent=steps[-1]["intent"] if steps else None,
        session_id=None,
        data={"results": results, "can_undo": bool(undo_actions)},
    )


def _collect_or_prepare(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    locale: str,
    session_id: str,
    state: dict,
    incoming_message: str | None,
) -> dict:
    steps = state.get("steps", [])
    idx = int(state.get("current_step_index", 0))
    if idx < len(steps) and incoming_message:
        current = steps[idx]
        intent = current["intent"]
        current_slots = _deserialize_slots(intent, current.get("slots", {}))
        merged = _merge_slots(
            intent,
            current_slots,
            _extract_slots_for_intent(intent, incoming_message, locale, current_slots=current_slots),
        )
        current["slots"] = _serialize_slots(intent, merged)

    next_idx, missing = _find_next_incomplete_step(steps, idx)
    if next_idx < len(steps):
        current = steps[next_idx]
        state["current_step_index"] = next_idx
        state["status"] = STATUS_COLLECTING
        save_session(session_id, state)
        slot_name = missing[0]
        return _build_response(
            reply=_slot_prompt_with_context(current["intent"], slot_name, locale, current.get("source_text")),
            status=STATUS_COLLECTING,
            intent=current["intent"],
            session_id=session_id,
            missing_slots=missing,
            pending_action=state,
            data={"requires_confirmation": state.get("requires_confirmation", False), "can_undo": False},
        )

    clear_session(session_id)
    return _execute_planned_steps(db, team_id=team_id, user_id=user_id, steps=steps, locale=locale)


def _initial_plan_response(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, message: str, locale: str) -> dict:
    steps, response = _plan_graph_steps(message, locale=locale)
    if response is not None:
        return response

    state = {"status": STATUS_COLLECTING, "steps": steps, "current_step_index": 0, "requires_confirmation": False}
    sid = create_session(state)
    return _collect_or_prepare(db, team_id=team_id, user_id=user_id, locale=locale, session_id=sid, state=state, incoming_message=None)


def _new_graph_session_state(*, steps: list[dict], mode: str, history: list[dict] | None = None) -> dict:
    return {
        "graph_version": GRAPH_SESSION_VERSION,
        "mode": _normalize_session_mode(mode),
        "history": _trim_conversation_history(history),
        "tasks": list(steps),
        "current_task": None,
        "loop_count": 0,
        "results": [],
        "reply_parts": [],
        "draft_steps": [],
        "waiting_for_user": False,
        "pending_question": None,
        "missing_slots": [],
    }


def _upgrade_graph_session_state(state: dict | None) -> dict | None:
    if not isinstance(state, dict):
        return None
    version = _normalize_optional_text(state.get("graph_version"))
    if version == GRAPH_SESSION_VERSION:
        upgraded = dict(state)
        upgraded["mode"] = _normalize_session_mode(upgraded.get("mode"))
        upgraded["history"] = _trim_conversation_history(upgraded.get("history") or [])
        return upgraded
    if version != "queue_v2":
        return None

    upgraded = dict(state)
    intents: list[str] = []
    current = upgraded.get("current_task")
    if isinstance(current, dict) and current.get("intent"):
        intents.append(current.get("intent"))
    for key in ("tasks", "draft_steps"):
        for step in upgraded.get(key) or []:
            if isinstance(step, dict) and step.get("intent"):
                intents.append(step.get("intent"))
    upgraded["graph_version"] = GRAPH_SESSION_VERSION
    upgraded["mode"] = SESSION_MODE_MUTATION if any(intent in MUTATING_INTENTS for intent in intents) else SESSION_MODE_CONVERSATION
    upgraded["history"] = _trim_conversation_history(upgraded.get("history") or [])
    return upgraded


def _build_conversation_passthrough_response(*, sid: str, session_state: dict, response: dict, user_message: str) -> tuple[str, dict, dict]:
    updated_state = _append_conversation_history(
        _reset_graph_runtime_state(session_state),
        user_message=user_message,
        assistant_reply=response.get("reply") or "",
        intent=response.get("intent"),
        status=response.get("status") or STATUS_UNSUPPORTED,
    )
    save_session(sid, updated_state)
    payload = dict(response)
    payload["session_id"] = sid
    data = dict(payload.get("data") or {})
    payload["data"] = _response_data(
        can_undo=bool(data.get("can_undo")),
        session_mode=SESSION_MODE_CONVERSATION,
        **{key: value for key, value in data.items() if key not in {"can_undo", "session_mode"}},
    )
    return sid, updated_state, payload


def _load_or_initialize_graph_session(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    locale: str,
    message: str,
    session_id: str | None,
) -> tuple[str | None, dict | None, dict | None]:
    if message == _LANGGRAPH_UNDO_MESSAGE:
        response = _undo_last_assistant_batch_local(
            db,
            team_id=team_id,
            user_id=user_id,
            locale=locale,
        )
        return None, None, response

    sid = _normalize_optional_text(session_id) or str(uuid.uuid4())
    existing = _upgrade_graph_session_state(get_session(sid))
    incoming = _normalize_optional_text(message)

    if existing:
        if incoming and _equals_any(incoming, TERM_SETS["cancel"]):
            clear_session(sid)
            response = _build_response(
                reply=translate(locale, "assistant.cancelled"),
                status=STATUS_CANCELLED,
                intent=existing.get("current_task", {}).get("intent") if isinstance(existing.get("current_task"), dict) else None,
                session_id=None,
                data=_response_data(can_undo=False),
            )
            return None, None, response

        if incoming and existing.get("waiting_for_user") and isinstance(existing.get("current_task"), dict):
            current = dict(existing["current_task"])
            intent = current.get("intent")
            current_slots = _deserialize_slots(intent, current.get("slots", {}))
            merged = _merge_slots(
                intent,
                current_slots,
                _extract_slots_for_intent(intent, incoming, locale, current_slots=current_slots),
            )
            current["slots"] = _serialize_slots(intent, merged)
            existing["current_task"] = current
            existing["waiting_for_user"] = False
            existing["pending_question"] = None
            existing["missing_slots"] = []
            save_session(sid, existing)
            return sid, existing, None

        if _normalize_session_mode(existing.get("mode")) == SESSION_MODE_CONVERSATION and incoming:
            steps, response = _plan_graph_steps(message, locale=locale, history=existing.get("history") or [])
            if response is not None:
                return _build_conversation_passthrough_response(sid=sid, session_state=existing, response=response, user_message=incoming)
            if steps:
                if _session_mode_for_steps(steps) == SESSION_MODE_MUTATION:
                    clear_session(sid)
                    sid = str(uuid.uuid4())
                    existing = _new_graph_session_state(steps=steps, mode=SESSION_MODE_MUTATION)
                else:
                    existing = _new_graph_session_state(
                        steps=steps,
                        mode=SESSION_MODE_CONVERSATION,
                        history=existing.get("history") or [],
                    )
                save_session(sid, existing)
                return sid, existing, None

        clear_session(sid)

    steps, response = _plan_graph_steps(message, locale=locale)
    if response is not None:
        return sid, None, response

    session_state = _new_graph_session_state(steps=steps or [], mode=_session_mode_for_steps(steps or []))
    save_session(sid, session_state)
    return sid, session_state, None


def _graph_prepare(state: AssistantGraphState) -> AssistantGraphState:
    # LangGraph threads persist state across runs, so clear transient runtime fields
    # before planning the next incoming message on the same thread.
    state["response"] = None
    state["step_result"] = {}
    state["incoming_message"] = None
    state["route"] = "prepare"

    db = state.get("db")
    owns_db = db is None
    if owns_db:
        db = _new_graph_db_session()
    try:
        team_id = _normalize_uuid(state["team_id"])
        user_id = _normalize_uuid(state["user_id"])
        locale = normalize_locale(state.get("locale") or "zh-CN")
        message = _normalize_text(state.get("message") or "")
        session_id = _normalize_optional_text(state.get("session_id"))

        sid, session_state, response = _load_or_initialize_graph_session(
            db,
            team_id=team_id,
            user_id=user_id,
            locale=locale,
            message=message,
            session_id=session_id,
        )
        if response is not None:
            state["response"] = response
            state["session_id"] = _normalize_optional_text(response.get("session_id")) if isinstance(response, dict) else None
            return state

        state["session_id"] = sid
        state["session_state"] = session_state or {}
        state["incoming_message"] = _normalize_optional_text(message)
        state["route"] = "loop_guard"
        return state
    finally:
        if owns_db and db is not None:
            db.close()


def _queue_guard_response(*, locale: str, session_mode: str, session_id: str | None) -> dict:
    return _build_response(
        reply=translate(locale, "assistant.too_many_steps", count=MAX_LOOP_COUNT),
        status=STATUS_UNSUPPORTED,
        intent=INTENT_UNSUPPORTED,
        session_id=session_id if session_mode == SESSION_MODE_CONVERSATION else None,
        data=_response_data(can_undo=False, session_mode=session_mode),
    )


def _queue_collecting_response(*, session_id: str, session_state: dict, locale: str) -> dict:
    pending_question = session_state.get("pending_question") or translate(locale, "assistant.slot_fallback")
    missing_slots = list(session_state.get("missing_slots") or [])
    current_task = session_state.get("current_task") if isinstance(session_state.get("current_task"), dict) else {}
    session_mode = _normalize_session_mode(session_state.get("mode"))
    return _build_response(
        reply=pending_question,
        status=STATUS_COLLECTING,
        intent=current_task.get("intent"),
        session_id=session_id,
        missing_slots=missing_slots,
        pending_action=session_state,
        data=_response_data(can_undo=False, session_mode=session_mode, requires_confirmation=False),
    )


def _finalize_queue_without_commit(*, session_state: dict, locale: str, session_id: str | None) -> dict:
    replies = [str(item).strip() for item in session_state.get("reply_parts", []) if str(item).strip()]
    results = list(session_state.get("results", []))
    session_mode = _normalize_session_mode(session_state.get("mode"))
    if not replies:
        return _build_response(
            reply=translate(locale, "assistant.unsupported"),
            status=STATUS_UNSUPPORTED,
            intent=INTENT_UNSUPPORTED,
            session_id=session_id if session_mode == SESSION_MODE_CONVERSATION else None,
            data=_response_data(can_undo=False, session_mode=session_mode, results=results),
        )
    final_intent = results[-1].get("intent") if results else None
    fallback_reply = "\n\n".join(replies)
    rendered_reply = _llm_render_readable_reply(locale=locale, results=results, fallback_reply=fallback_reply)
    return _build_response(
        reply=rendered_reply,
        status=STATUS_EXECUTED,
        intent=final_intent,
        session_id=session_id if session_mode == SESSION_MODE_CONVERSATION else None,
        data=_response_data(can_undo=False, session_mode=session_mode, results=results),
    )


def _rollback_successful_actions(db: Session, actions: list[dict]) -> None:
    if not actions:
        return
    now = dt.datetime.now(dt.timezone.utc)
    for action in reversed(actions):
        intent = action.get("intent")
        record_id = action.get("record_id")
        if not record_id:
            continue
        if intent == INTENT_CREATE_FINANCE:
            record = db.query(FinanceRecord).filter(FinanceRecord.id == uuid.UUID(record_id)).first()
            if record and record.deleted_at is None:
                record.deleted_at = now
                db.add(record)
        elif intent == INTENT_CREATE_SCHEDULE:
            record = db.query(Schedule).filter(Schedule.id == uuid.UUID(record_id)).first()
            if record and record.deleted_at is None:
                record.deleted_at = now
                db.add(record)
    db.commit()


def _schedule_subgraph(db: Session, *, step: dict, team_id: uuid.UUID, user_id: uuid.UUID, locale: str) -> dict:
    intent = step.get("intent")
    if intent == INTENT_QUERY_SCHEDULE:
        result = _execute_step(db, step=step, team_id=team_id, user_id=user_id, locale=locale)
        return {"status": STATUS_EXECUTED, "result": result}
    if intent != INTENT_CREATE_SCHEDULE:
        return {"status": STATUS_UNSUPPORTED, "result": {"intent": intent, "status": STATUS_UNSUPPORTED, "reply": translate(locale, "assistant.unsupported"), "data": None}}
    slots = _deserialize_slots(intent, step.get("slots", {}))
    missing = _missing_slots(intent, slots)
    if missing:
        return {
            "status": STATUS_COLLECTING,
            "missing_slots": missing,
            "reply": _slot_prompt_with_context(intent, missing[0], locale, step.get("source_text")),
            "step": {"intent": intent, "slots": _serialize_slots(intent, slots), "source_text": step.get("source_text")},
        }
    return {"status": "ready", "step": {"intent": intent, "slots": _serialize_slots(intent, slots), "source_text": step.get("source_text")}}


def _expense_subgraph(db: Session, *, step: dict, team_id: uuid.UUID, user_id: uuid.UUID, locale: str) -> dict:
    intent = step.get("intent")
    if intent == INTENT_QUERY_FINANCE:
        result = _execute_step(db, step=step, team_id=team_id, user_id=user_id, locale=locale)
        return {"status": STATUS_EXECUTED, "result": result}
    if intent != INTENT_CREATE_FINANCE:
        return {"status": STATUS_UNSUPPORTED, "result": {"intent": intent, "status": STATUS_UNSUPPORTED, "reply": translate(locale, "assistant.unsupported"), "data": None}}
    slots = _deserialize_slots(intent, step.get("slots", {}))
    missing = _missing_slots(intent, slots)
    if missing:
        return {
            "status": STATUS_COLLECTING,
            "missing_slots": missing,
            "reply": _slot_prompt_with_context(intent, missing[0], locale, step.get("source_text")),
            "step": {"intent": intent, "slots": _serialize_slots(intent, slots), "source_text": step.get("source_text")},
        }
    return {"status": "ready", "step": {"intent": intent, "slots": _serialize_slots(intent, slots), "source_text": step.get("source_text")}}


def _graph_loop_guard(state: AssistantGraphState) -> AssistantGraphState:
    if state.get("response"):
        return state
    session_state = state.get("session_state") or {}
    locale = normalize_locale(state.get("locale") or "zh-CN")
    session_id = _normalize_optional_text(state.get("session_id"))
    session_mode = _normalize_session_mode(session_state.get("mode"))

    if int(session_state.get("loop_count", 0)) > MAX_LOOP_COUNT:
        response = _queue_guard_response(locale=locale, session_mode=session_mode, session_id=session_id)
        if session_mode == SESSION_MODE_CONVERSATION and session_id:
            session_state = _append_conversation_history(
                _reset_graph_runtime_state(session_state),
                user_message=state.get("incoming_message"),
                assistant_reply=response.get("reply") or "",
                intent=response.get("intent"),
                status=response.get("status") or STATUS_UNSUPPORTED,
            )
            save_session(session_id, session_state)
            state["session_id"] = session_id
        else:
            clear_session(session_id)
            state["session_id"] = None
        state["response"] = response
        state["route"] = "done"
        return state

    if session_state.get("waiting_for_user"):
        if session_id:
            save_session(session_id, session_state)
        state["response"] = _queue_collecting_response(session_id=session_id or "", session_state=session_state, locale=locale)
        state["route"] = "done"
        return state

    current_task = session_state.get("current_task")
    tasks = list(session_state.get("tasks") or [])
    if not current_task and tasks:
        state["route"] = "dequeue"
        return state
    if not current_task and not tasks:
        if session_state.get("draft_steps"):
            state["route"] = "commit"
            return state
        response = _finalize_queue_without_commit(session_state=session_state, locale=locale, session_id=session_id)
        if session_mode == SESSION_MODE_CONVERSATION and session_id:
            session_state = _append_conversation_history(
                _reset_graph_runtime_state(session_state),
                user_message=state.get("incoming_message"),
                assistant_reply=response.get("reply") or "",
                intent=response.get("intent"),
                status=response.get("status") or STATUS_EXECUTED,
            )
            save_session(session_id, session_state)
            state["session_id"] = session_id
        else:
            clear_session(session_id)
            state["session_id"] = None
        state["response"] = response
        state["route"] = "done"
        return state

    state["route"] = "route_subgraph"
    return state


def _graph_dequeue_task(state: AssistantGraphState) -> AssistantGraphState:
    session_state = state.get("session_state") or {}
    tasks = list(session_state.get("tasks") or [])
    if not tasks:
        state["route"] = "loop_guard"
        return state
    current = tasks.pop(0)
    session_state["tasks"] = tasks
    session_state["current_task"] = current
    session_state["loop_count"] = int(session_state.get("loop_count", 0)) + 1
    session_state["waiting_for_user"] = False
    session_state["pending_question"] = None
    session_state["missing_slots"] = []
    state["session_state"] = session_state
    state["route"] = "route_subgraph"
    return state


def _graph_route_subgraph(state: AssistantGraphState) -> AssistantGraphState:
    session_state = state.get("session_state") or {}
    current = session_state.get("current_task")
    if not isinstance(current, dict):
        state["route"] = "loop_guard"
        return state
    intent = current.get("intent")
    if intent in {INTENT_CREATE_SCHEDULE, INTENT_QUERY_SCHEDULE}:
        state["route"] = "schedule"
    elif intent in {INTENT_CREATE_FINANCE, INTENT_QUERY_FINANCE}:
        state["route"] = "expense"
    else:
        locale = normalize_locale(state.get("locale") or "zh-CN")
        state["step_result"] = {
            "status": STATUS_UNSUPPORTED,
            "result": {"intent": intent, "status": STATUS_UNSUPPORTED, "reply": translate(locale, "assistant.unsupported"), "data": None},
        }
        state["route"] = "collect_result"
    return state


def _graph_schedule_subgraph(state: AssistantGraphState) -> AssistantGraphState:
    db = state.get("db")
    owns_db = db is None
    if owns_db:
        db = _new_graph_db_session()
    try:
        team_id = _normalize_uuid(state["team_id"])
        user_id = _normalize_uuid(state["user_id"])
        locale = normalize_locale(state.get("locale") or "zh-CN")
        session_state = state.get("session_state") or {}
        current = session_state.get("current_task") if isinstance(session_state.get("current_task"), dict) else {}
        state["step_result"] = _schedule_subgraph(db, step=current, team_id=team_id, user_id=user_id, locale=locale)
        state["route"] = "collect_result"
        return state
    finally:
        if owns_db and db is not None:
            db.close()


def _graph_expense_subgraph(state: AssistantGraphState) -> AssistantGraphState:
    db = state.get("db")
    owns_db = db is None
    if owns_db:
        db = _new_graph_db_session()
    try:
        team_id = _normalize_uuid(state["team_id"])
        user_id = _normalize_uuid(state["user_id"])
        locale = normalize_locale(state.get("locale") or "zh-CN")
        session_state = state.get("session_state") or {}
        current = session_state.get("current_task") if isinstance(session_state.get("current_task"), dict) else {}
        state["step_result"] = _expense_subgraph(db, step=current, team_id=team_id, user_id=user_id, locale=locale)
        state["route"] = "collect_result"
        return state
    finally:
        if owns_db and db is not None:
            db.close()


def _graph_collect_result(state: AssistantGraphState) -> AssistantGraphState:
    session_state = state.get("session_state") or {}
    current = session_state.get("current_task") if isinstance(session_state.get("current_task"), dict) else {}
    step_result = state.get("step_result") or {}

    status = step_result.get("status")
    if status == STATUS_COLLECTING:
        session_state["current_task"] = step_result.get("step", current)
        session_state["waiting_for_user"] = True
        session_state["pending_question"] = step_result.get("reply")
        session_state["missing_slots"] = list(step_result.get("missing_slots") or [])
        state["session_state"] = session_state
        state["route"] = "loop_guard"
        return state

    if status == "ready":
        draft_steps = list(session_state.get("draft_steps") or [])
        draft_steps.append(step_result.get("step", current))
        session_state["draft_steps"] = draft_steps
        session_state["current_task"] = None
        session_state["waiting_for_user"] = False
        session_state["pending_question"] = None
        session_state["missing_slots"] = []
        state["session_state"] = session_state
        state["route"] = "loop_guard"
        return state

    result = step_result.get("result") if isinstance(step_result.get("result"), dict) else None
    if status == STATUS_EXECUTED and isinstance(result, dict):
        results = list(session_state.get("results") or [])
        results.append({"intent": result.get("intent"), "status": result.get("status"), "data": result.get("data")})
        session_state["results"] = results
        reply_parts = list(session_state.get("reply_parts") or [])
        if result.get("reply"):
            reply_parts.append(result.get("reply"))
        session_state["reply_parts"] = reply_parts
        session_state["current_task"] = None
        state["session_state"] = session_state
        state["route"] = "loop_guard"
        return state

    locale = normalize_locale(state.get("locale") or "zh-CN")
    session_id = _normalize_optional_text(state.get("session_id"))
    session_mode = _normalize_session_mode(session_state.get("mode"))
    reply = result.get("reply") if isinstance(result, dict) and result.get("reply") else translate(locale, "assistant.unsupported")
    response = _build_response(
        reply=reply,
        status=STATUS_UNSUPPORTED,
        intent=result.get("intent") if isinstance(result, dict) else INTENT_UNSUPPORTED,
        session_id=session_id if session_mode == SESSION_MODE_CONVERSATION else None,
        data=_response_data(can_undo=False, session_mode=session_mode, results=session_state.get("results") or []),
    )
    if session_mode == SESSION_MODE_CONVERSATION and session_id:
        session_state = _append_conversation_history(
            _reset_graph_runtime_state(session_state),
            user_message=state.get("incoming_message"),
            assistant_reply=reply,
            intent=response.get("intent"),
            status=response.get("status") or STATUS_UNSUPPORTED,
        )
        save_session(session_id, session_state)
        state["session_id"] = session_id
    else:
        clear_session(session_id)
        state["session_id"] = None
    state["response"] = response
    state["route"] = "done"
    return state


def _graph_commit_batch(state: AssistantGraphState) -> AssistantGraphState:
    db = state.get("db")
    owns_db = db is None
    if owns_db:
        db = _new_graph_db_session()
    try:
        team_id = _normalize_uuid(state["team_id"])
        user_id = _normalize_uuid(state["user_id"])
        locale = normalize_locale(state.get("locale") or "zh-CN")
        session_id = _normalize_optional_text(state.get("session_id"))
        session_state = state.get("session_state") or {}
        session_mode = _normalize_session_mode(session_state.get("mode"))
        draft_steps = list(session_state.get("draft_steps") or [])

        if int(session_state.get("loop_count", 0)) > MAX_LOOP_COUNT:
            clear_session(session_id)
            state["response"] = _queue_guard_response(locale=locale, session_mode=session_mode, session_id=None)
            state["session_id"] = None
            state["route"] = "done"
            return state

        replies = [str(item).strip() for item in session_state.get("reply_parts", []) if str(item).strip()]
        results = list(session_state.get("results") or [])
        undo_actions: list[dict] = []

        for step in draft_steps:
            result = _execute_step(db, step=step, team_id=team_id, user_id=user_id, locale=locale)
            if result.get("status") != STATUS_EXECUTED:
                _rollback_successful_actions(db, undo_actions)
                clear_session(session_id)
                state["response"] = _build_response(
                    reply=result.get("reply") or translate(locale, "assistant.internal_error"),
                    status=STATUS_UNSUPPORTED,
                    intent=result.get("intent"),
                    session_id=None,
                    data=_response_data(can_undo=False, session_mode=session_mode, results=results),
                )
                state["session_id"] = None
                state["route"] = "done"
                return state
            if result.get("reply"):
                replies.append(result["reply"])
            results.append({"intent": result.get("intent"), "status": result.get("status"), "data": result.get("data")})
            if result.get("undo"):
                undo_actions.append(result["undo"])

        _save_undo_batch(team_id, user_id, undo_actions)
        fallback_reply = "\n\n".join(replies) if replies else translate(locale, "assistant.unsupported")
        rendered_reply = _llm_render_readable_reply(locale=locale, results=results, fallback_reply=fallback_reply)
        clear_session(session_id)
        state["response"] = _build_response(
            reply=rendered_reply,
            status=STATUS_EXECUTED,
            intent=results[-1].get("intent") if results else None,
            session_id=None,
            data=_response_data(can_undo=bool(undo_actions), session_mode=session_mode, results=results),
        )
        state["session_id"] = None
        state["route"] = "done"
        return state
    finally:
        if owns_db and db is not None:
            db.close()


def _route_from_state(state: AssistantGraphState) -> str:
    return str(state.get("route") or "done")


def _build_assistant_graph():
    if StateGraph is None:
        return None
    graph = StateGraph(AssistantGraphState)
    graph.add_node("prepare", _graph_prepare)
    graph.add_node("loop_guard", _graph_loop_guard)
    graph.add_node("dequeue_task", _graph_dequeue_task)
    graph.add_node("route_subgraph", _graph_route_subgraph)
    graph.add_node("schedule_subgraph", _graph_schedule_subgraph)
    graph.add_node("expense_subgraph", _graph_expense_subgraph)
    graph.add_node("collect_result", _graph_collect_result)
    graph.add_node("commit_batch", _graph_commit_batch)

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges(
        "prepare",
        _route_from_state,
        {
            "loop_guard": "loop_guard",
            "done": END,
        },
    )
    graph.add_conditional_edges(
        "loop_guard",
        _route_from_state,
        {
            "dequeue": "dequeue_task",
            "route_subgraph": "route_subgraph",
            "commit": "commit_batch",
            "done": END,
        },
    )
    graph.add_conditional_edges(
        "dequeue_task",
        _route_from_state,
        {
            "route_subgraph": "route_subgraph",
            "loop_guard": "loop_guard",
        },
    )
    graph.add_conditional_edges(
        "route_subgraph",
        _route_from_state,
        {
            "schedule": "schedule_subgraph",
            "expense": "expense_subgraph",
            "collect_result": "collect_result",
            "loop_guard": "loop_guard",
        },
    )
    graph.add_edge("schedule_subgraph", "collect_result")
    graph.add_edge("expense_subgraph", "collect_result")
    graph.add_conditional_edges(
        "collect_result",
        _route_from_state,
        {
            "loop_guard": "loop_guard",
            "done": END,
        },
    )
    graph.add_conditional_edges(
        "commit_batch",
        _route_from_state,
        {
            "done": END,
        },
    )
    return graph.compile()


def _get_assistant_graph():
    global _ASSISTANT_GRAPH
    if _ASSISTANT_GRAPH is None:
        _ASSISTANT_GRAPH = _build_assistant_graph()
    return _ASSISTANT_GRAPH


def _execute_assistant_langgraph(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    session_id: str | None,
    locale: str,
) -> dict:
    _apply_langsmith_env_from_settings()
    thread_id = _resolve_langgraph_thread_id(session_id)
    _ensure_langgraph_thread(thread_id=thread_id, team_id=team_id, user_id=user_id, locale=locale)
    run_payload = {
        "assistant_id": _langgraph_assistant_id(),
        "if_not_exists": "create",
        "input": {
            "team_id": str(team_id),
            "user_id": str(user_id),
            "locale": locale,
            "message": message,
            "session_id": thread_id,
            "response": None,
            "step_result": None,
            "incoming_message": None,
            "route": None,
        },
        "metadata": {
            "team_id": str(team_id),
            "user_id": str(user_id),
            "locale": locale,
            "engine": _assistant_engine(),
            "source": "teamhome-api",
        },
        "config": {
            "tags": ["teamhome", "assistant", "langgraph"],
            "configurable": {"thread_id": thread_id},
        },
    }
    payload = _post_langgraph_json(f"/threads/{thread_id}/runs/wait", run_payload)
    response = _extract_langgraph_response(payload)
    session_mode = None
    if isinstance(response.get("data"), dict):
        session_mode = _normalize_optional_text(response["data"].get("session_mode"))
    if not response.get("session_id") and (response.get("status") == STATUS_COLLECTING or session_mode == SESSION_MODE_CONVERSATION):
        response["session_id"] = thread_id
    return _attach_langgraph_visual_state(response, thread_id=thread_id)


def _execute_assistant_legacy(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    session_id: str | None,
    locale: str = "zh-CN",
) -> dict:
    locale = normalize_locale(locale)
    if not is_team_member(db, team_id=team_id, user_id=user_id):
        raise PermissionError("Not a team member")

    text = _normalize_text(message)
    if not text:
        return _build_response(reply=translate(locale, "assistant.empty_message"), status=STATUS_UNSUPPORTED, intent=None, session_id=session_id, data={"can_undo": False})

    try:
        state = get_session(session_id)
        if not state:
            return _initial_plan_response(db, team_id=team_id, user_id=user_id, message=text, locale=locale)

        steps = state.get("steps", [])
        idx = int(state.get("current_step_index", 0))
        current_intent = steps[idx]["intent"] if idx < len(steps) else None

        if _equals_any(text, TERM_SETS["cancel"]):
            clear_session(session_id)
            return _build_response(reply=translate(locale, "assistant.cancelled"), status=STATUS_CANCELLED, intent=current_intent, session_id=None, data={"can_undo": False})

        if state.get("status") == "awaiting_confirmation":
            # Backward compatibility for sessions created by older logic:
            # execute directly instead of waiting for explicit confirmation.
            clear_session(session_id)
            return _execute_planned_steps(db, team_id=team_id, user_id=user_id, steps=steps, locale=locale)

        return _collect_or_prepare(
            db,
            team_id=team_id,
            user_id=user_id,
            locale=locale,
            session_id=session_id or "",
            state=state,
            incoming_message=text,
        )
    except Exception:
        clear_session(session_id)
        return _build_response(reply=translate(locale, "assistant.internal_error"), status=STATUS_UNSUPPORTED, intent=INTENT_UNSUPPORTED, session_id=None, data={"can_undo": False})


def execute_assistant(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    session_id: str | None,
    locale: str = "zh-CN",
) -> dict:
    if _use_langgraph_engine():
        locale = normalize_locale(locale)
        if not is_team_member(db, team_id=team_id, user_id=user_id):
            raise PermissionError("Not a team member")
        text = _normalize_text(message)
        if not text:
            return _build_response(
                reply=translate(locale, "assistant.empty_message"),
                status=STATUS_UNSUPPORTED,
                intent=None,
                session_id=session_id,
                data={"can_undo": False},
            )
        try:
            return _execute_assistant_langgraph(
                db,
                team_id=team_id,
                user_id=user_id,
                message=text,
                session_id=session_id,
                locale=locale,
            )
        except Exception:
            clear_session(session_id)
            return _build_response(
                reply=translate(locale, "assistant.internal_error"),
                status=STATUS_UNSUPPORTED,
                intent=INTENT_UNSUPPORTED,
                session_id=None,
                data={"can_undo": False},
            )

    return _execute_assistant_legacy(
        db,
        team_id=team_id,
        user_id=user_id,
        message=message,
        session_id=session_id,
        locale=locale,
    )


def get_orchestration_debug() -> dict:
    runtime_engine = _assistant_engine()
    langsmith = _langsmith_debug_info()
    nodes = [
        {"id": "START", "label": "START"},
        {"id": "prepare", "label": "prepare"},
        {"id": "loop_guard", "label": "loop_guard"},
        {"id": "dequeue_task", "label": "dequeue_task"},
        {"id": "route_subgraph", "label": "route_subgraph"},
        {"id": "schedule_subgraph", "label": "schedule_subgraph"},
        {"id": "expense_subgraph", "label": "expense_subgraph"},
        {"id": "collect_result", "label": "collect_result"},
        {"id": "commit_batch", "label": "commit_batch"},
        {"id": "END", "label": "END"},
    ]
    edges = [
        {"source": "START", "target": "prepare"},
        {"source": "prepare", "target": "loop_guard"},
        {"source": "loop_guard", "target": "dequeue_task"},
        {"source": "dequeue_task", "target": "route_subgraph"},
        {"source": "route_subgraph", "target": "schedule_subgraph"},
        {"source": "route_subgraph", "target": "expense_subgraph"},
        {"source": "schedule_subgraph", "target": "collect_result"},
        {"source": "expense_subgraph", "target": "collect_result"},
        {"source": "collect_result", "target": "loop_guard"},
        {"source": "loop_guard", "target": "commit_batch"},
        {"source": "commit_batch", "target": "END"},
    ]
    mermaid = (
        "graph TD\n"
        "  START --> prepare\n"
        "  prepare --> loop_guard\n"
        "  loop_guard --> dequeue_task\n"
        "  dequeue_task --> route_subgraph\n"
        "  route_subgraph --> schedule_subgraph\n"
        "  route_subgraph --> expense_subgraph\n"
        "  schedule_subgraph --> collect_result\n"
        "  expense_subgraph --> collect_result\n"
        "  collect_result --> loop_guard\n"
        "  loop_guard --> commit_batch\n"
        "  commit_batch --> END"
    )
    raw_nodes = None
    raw_edges = None
    raw_mermaid = None

    app = _get_assistant_graph()
    if app and hasattr(app, "get_graph"):
        try:
            g = app.get_graph()
            if hasattr(g, "draw_mermaid"):
                drawn = g.draw_mermaid()
                if isinstance(drawn, str) and drawn.strip():
                    raw_mermaid = drawn
            graph_nodes = getattr(g, "nodes", None)
            graph_edges = getattr(g, "edges", None)
            parsed_nodes = []
            if isinstance(graph_nodes, dict):
                for key in graph_nodes.keys():
                    parsed_nodes.append({"id": str(key), "label": str(key)})
            if parsed_nodes:
                raw_nodes = parsed_nodes
            parsed_edges = []
            if isinstance(graph_edges, list):
                for item in graph_edges:
                    src = getattr(item, "source", None) or getattr(item, "start", None)
                    dst = getattr(item, "target", None) or getattr(item, "end", None)
                    if src is not None and dst is not None:
                        parsed_edges.append({"source": str(src), "target": str(dst)})
            if parsed_edges:
                raw_edges = parsed_edges
        except Exception:
            pass

    return {
        "engine": runtime_engine,
        "langgraph_available": StateGraph is not None,
        "langgraph_enabled": _use_langgraph_engine(),
        "langgraph_api": {
            "assistant_id": _langgraph_assistant_id(),
            "base_urls": _langgraph_base_urls(),
        },
        "langsmith": langsmith,
        "nodes": nodes,
        "edges": edges,
        "mermaid": mermaid,
        "raw_nodes": raw_nodes,
        "raw_edges": raw_edges,
        "raw_mermaid": raw_mermaid,
    }


def _undo_last_assistant_batch_local(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    locale: str = "zh-CN",
) -> dict:
    locale = normalize_locale(locale)
    actions = pop_undo_batch(team_id, user_id)
    if not actions:
        return _build_response(reply=translate(locale, "assistant.undo_empty"), status=STATUS_UNSUPPORTED, intent="undo", session_id=None, data={"can_undo": False})

    now = dt.datetime.now(dt.timezone.utc)
    for action in reversed(actions):
        intent = action.get("intent")
        record_id = action.get("record_id")
        if not record_id:
            continue
        if intent == INTENT_CREATE_FINANCE:
            record = db.query(FinanceRecord).filter(FinanceRecord.id == uuid.UUID(record_id)).first()
            if record and record.deleted_at is None:
                record.deleted_at = now
                db.add(record)
        elif intent == INTENT_CREATE_SCHEDULE:
            record = db.query(Schedule).filter(Schedule.id == uuid.UUID(record_id)).first()
            if record and record.deleted_at is None:
                record.deleted_at = now
                db.add(record)
    db.commit()
    return _build_response(reply=translate(locale, "assistant.undo_done"), status=STATUS_EXECUTED, intent="undo", session_id=None, data={"can_undo": False})


def undo_last_assistant_batch(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    locale: str = "zh-CN",
) -> dict:
    locale = normalize_locale(locale)
    if _use_langgraph_engine():
        try:
            undo_thread_id = str(uuid.uuid5(_LANGGRAPH_THREAD_NAMESPACE, f"undo:{team_id}:{user_id}"))
            return _execute_assistant_langgraph(
                db,
                team_id=team_id,
                user_id=user_id,
                message=_LANGGRAPH_UNDO_MESSAGE,
                session_id=undo_thread_id,
                locale=locale,
            )
        except Exception:
            return _build_response(
                reply=translate(locale, "assistant.internal_error"),
                status=STATUS_UNSUPPORTED,
                intent=INTENT_UNSUPPORTED,
                session_id=None,
                data={"can_undo": False},
            )
    return _undo_last_assistant_batch_local(
        db,
        team_id=team_id,
        user_id=user_id,
        locale=locale,
    )
