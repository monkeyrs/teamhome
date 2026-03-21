from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid

from sqlalchemy.orm import Session

from app.core.i18n import RELATIVE_DAY_TERMS, TERM_SETS, normalize_locale, translate
from app.crud.finance import create_finance_record
from app.crud.schedule import create_schedule, list_schedules
from app.crud.team import is_team_member
from app.models.finance import FinanceRecord
from app.models.schedule import Schedule
from app.services.assistant_session_service import clear_session, create_session, get_session, save_session
from app.services.llm.assistant import answer_finance_question
from app.services.llm.openrouter import get_llm_client
from app.services.llm.parser import parse_finance_text, parse_schedule_text


INTENT_CREATE_FINANCE = "create_finance"
INTENT_QUERY_FINANCE = "query_finance"
INTENT_CREATE_SCHEDULE = "create_schedule"
INTENT_QUERY_SCHEDULE = "query_schedule"
INTENT_UNSUPPORTED = "unsupported"

STATUS_COLLECTING = "collecting"
STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATUS_EXECUTED = "executed"
STATUS_CANCELLED = "cancelled"
STATUS_UNSUPPORTED = "unsupported"

MAX_PLAN_STEPS = 5
MUTATING_INTENTS = {INTENT_CREATE_FINANCE, INTENT_CREATE_SCHEDULE}
ALLOWED_INTENTS = {
    INTENT_CREATE_FINANCE,
    INTENT_QUERY_FINANCE,
    INTENT_CREATE_SCHEDULE,
    INTENT_QUERY_SCHEDULE,
    INTENT_UNSUPPORTED,
}

_UNDO_BATCHES: dict[tuple[str, str], list[dict]] = {}
_BARE_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


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


def _normalize_finance_category_value(value: object) -> str | None:
    text = _normalize_optional_text(value)
    if not text:
        return None
    mapping = {
        "food": "餐费",
        "meal": "餐费",
        "transport": "交通",
        "traffic": "交通",
        "taxi": "交通",
        "lodging": "住宿",
        "hotel": "住宿",
        "accommodation": "住宿",
    }
    return mapping.get(text.casefold(), text)


def _format_dt(value: dt.datetime | None, locale: str) -> str:
    if value is None:
        return translate(locale, "assistant.not_set")
    local_value = value.astimezone() if value.tzinfo else value
    return local_value.strftime("%Y-%m-%d %H:%M")


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


def _extract_finance_slots(message: str) -> dict:
    text = _normalize_text(message)
    parsed = parse_finance_text(text)
    category = _normalize_finance_category_value(parsed.get("category"))
    if category == "other":
        category = None
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
    has_schedule_hint = has_explicit_schedule_hint or (
        has_schedule_time_parse and not has_amount and not has_finance_hint and not has_create_hint
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


def _plan_intents(message: str) -> tuple[list[str], bool]:
    text = _normalize_text(message)
    fallback = _heuristic_intents(text)
    if fallback == [INTENT_UNSUPPORTED]:
        fallback = []

    client = get_llm_client()
    if not client:
        return (fallback or [INTENT_UNSUPPORTED], False)

    sysdate = _local_now().strftime("%Y-%m-%d %H:%M:%S %z")
    system = (
        "You are a schedule and finance assistant planner. Light small talk is allowed.\n"
        "Always reason and classify in English, independent from the user's language.\n"
        f"Current datetime is: {sysdate}.\n"
        "You have exactly 4 skills:\n"
        "1) create_finance\n"
        "- purpose: create a finance record\n"
        "- required params: amount(number), type(expense|income), category(nature string)\n"
        "- optional params: occurred_at(ISO8601), location(string), note(string)\n"
        "2) query_finance\n"
        "- purpose: query finance records/summary\n"
        "- required params: question(string)\n"
        "- optional params: none\n"
        "3) create_schedule\n"
        "- purpose: create a schedule\n"
        "- required params: title(string), start_time(ISO8601), end_time(ISO8601)\n"
        "- optional params: is_all_day(boolean), location(string), description(string)\n"
        "4) query_schedule\n"
        "- purpose: query schedules\n"
        "- required params: none\n"
        "- optional params: window_start(ISO8601), window_end(ISO8601), label(string)\n"
        "Planning rules:\n"
        "- Semantic understanding has higher priority than keyword hits.\n"
        "- A single message may contain multiple intents; return ordered steps.\n"
        f"- Maximum {MAX_PLAN_STEPS} steps. If more than {MAX_PLAN_STEPS} are required, set need_split=true.\n"
        "- Time/activity statements are schedule intents, not finance intents.\n"
        "- query_* only when user asks to check existing data.\n"
        "- create_* only when user asks to add/create/record data.\n"
        "- If message is only small talk, return unsupported (empty steps).\n"
        "Return strict JSON only with keys: steps, need_split, reason."
    )
    user = (
        f"User message: {text}\n"
        'Return JSON: {"steps":[{"intent":"create_finance|query_finance|create_schedule|query_schedule"}],"need_split":false,"reason":"..."}'
    )
    try:
        data = client.chat_json(system=system, user=user) or {}
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
    if len(intents) > MAX_PLAN_STEPS:
        return ([], True)
    if intents:
        return (intents, False)
    return (fallback or [INTENT_UNSUPPORTED], False)


def _tool_slot_guide(intent: str) -> str:
    if intent == INTENT_CREATE_FINANCE:
        return (
            "intent=create_finance\n"
            "required: amount(number), type(expense|income), category(nature string)\n"
            "optional: occurred_at(ISO8601), location(string), note(string)"
        )
    if intent == INTENT_CREATE_SCHEDULE:
        return (
            "intent=create_schedule\n"
            "required: title(string), start_time(ISO8601), end_time(ISO8601)\n"
            "optional: is_all_day(boolean), location(string), description(string)"
        )
    if intent == INTENT_QUERY_SCHEDULE:
        return (
            "intent=query_schedule\n"
            "optional: window_start(ISO8601), window_end(ISO8601), label(string)"
        )
    if intent == INTENT_QUERY_FINANCE:
        return "intent=query_finance\nrequired: question(string)"
    return "intent=unsupported"


def _coerce_llm_slots(intent: str, slots: dict) -> dict:
    normalized: dict = {}
    if intent == INTENT_CREATE_FINANCE:
        amount = slots.get("amount")
        if amount not in (None, ""):
            try:
                normalized["amount"] = float(amount)
            except Exception:
                pass
        record_type = str(slots.get("type") or "").strip().lower()
        if record_type in {"expense", "income"}:
            normalized["type"] = record_type
        category = slots.get("category")
        if category not in (None, ""):
            normalized["category"] = _normalize_finance_category_value(category)
        occurred_at = _parse_iso_datetime(slots.get("occurred_at"))
        if occurred_at:
            normalized["occurred_at"] = occurred_at.isoformat()
        location = _normalize_optional_text(slots.get("location"))
        if location:
            normalized["location"] = location
        note = _normalize_optional_text(slots.get("note"))
        if note:
            normalized["note"] = note
        return normalized

    if intent == INTENT_CREATE_SCHEDULE:
        title = slots.get("title")
        if title not in (None, ""):
            normalized["title"] = str(title).strip()
        for key in ("start_time", "end_time"):
            parsed = _parse_iso_datetime(slots.get(key))
            if parsed:
                normalized[key] = parsed
        if isinstance(slots.get("is_all_day"), bool):
            normalized["is_all_day"] = slots["is_all_day"]
        location = _normalize_optional_text(slots.get("location"))
        if location:
            normalized["location"] = location
        description = _normalize_optional_text(slots.get("description"))
        if description:
            normalized["description"] = description
        return normalized

    if intent == INTENT_QUERY_SCHEDULE:
        for key in ("window_start", "window_end"):
            parsed = _parse_iso_datetime(slots.get(key))
            if parsed:
                normalized[key] = parsed
        label = slots.get("label")
        if label not in (None, ""):
            normalized["label"] = str(label).strip()
        return normalized

    if intent == INTENT_QUERY_FINANCE:
        question = slots.get("question")
        if question not in (None, ""):
            normalized["question"] = str(question).strip()
        return normalized

    return normalized


def _llm_extract_slots(intent: str, *, message: str, current_slots: dict) -> dict:
    client = get_llm_client()
    if not client:
        return {}

    sysdate = _local_now().strftime("%Y-%m-%d %H:%M:%S %z")
    system = (
        "You are an assistant parameter extractor for one selected skill.\n"
        "Always reason and parse in English, regardless of user language.\n"
        f"Current datetime is: {sysdate}.\n"
        "Extract only parameters for the given intent.\n"
        "Do not invent missing values.\n"
        "If user only provides partial fields, keep others null.\n"
        "Return JSON only."
    )
    user = (
        f"Tool:\n{_tool_slot_guide(intent)}\n\n"
        f"Current slots: {current_slots}\n"
        f"User message: {message}\n\n"
        'Return JSON: {"slots": {...}}'
    )
    try:
        data = client.chat_json(system=system, user=user) or {}
    except Exception:
        return {}
    slots = data.get("slots")
    if not isinstance(slots, dict):
        return {}
    return _coerce_llm_slots(intent, slots)


def _required_slots(intent: str) -> list[str]:
    if intent == INTENT_CREATE_FINANCE:
        return ["amount", "type", "category"]
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


def _extract_slots_for_intent(intent: str, message: str, locale: str, current_slots: dict | None = None) -> dict:
    base: dict = {}
    if intent == INTENT_CREATE_FINANCE:
        base = _extract_finance_slots(message)
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

    llm_context = dict(current_slots or {})
    for key, value in base.items():
        if value not in (None, ""):
            llm_context[key] = value
    llm_slots = _llm_extract_slots(intent, message=message, current_slots=llm_context)
    merged = dict(base)
    for key, value in llm_slots.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _merge_slots(intent: str, current_slots: dict, incoming_slots: dict) -> dict:
    merged = dict(current_slots or {})
    for key, value in (incoming_slots or {}).items():
        if value not in (None, ""):
            if intent == INTENT_CREATE_FINANCE and key == "note" and merged.get("note") not in (None, ""):
                continue
            merged[key] = value
    return _with_default_schedule_end(merged) if intent == INTENT_CREATE_SCHEDULE else merged


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


def _make_initial_steps(intents: list[str], message: str, locale: str) -> list[dict]:
    steps: list[dict] = []
    for intent in intents:
        if intent not in ALLOWED_INTENTS or intent == INTENT_UNSUPPORTED:
            continue
        slots = _extract_slots_for_intent(intent, message, locale, current_slots=None)
        steps.append({"intent": intent, "slots": _serialize_slots(intent, slots)})
    return steps


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


def _execute_step(db: Session, *, step: dict, team_id: uuid.UUID, user_id: uuid.UUID, locale: str) -> dict:
    intent = step["intent"]
    slots = _deserialize_slots(intent, step.get("slots", {}))
    if intent == INTENT_QUERY_FINANCE:
        result = answer_finance_question(db, team_id=team_id, question=slots.get("question") or "", locale=locale)
        return {"status": STATUS_EXECUTED, "intent": intent, "reply": result.get("answer", ""), "data": result.get("data")}

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
        record = create_finance_record(
            db,
            team_id=team_id,
            user_id=user_id,
            amount=amount,
            record_type=slots["type"],
            category=slots["category"],
            occurred_at=occurred_at,
            location=_normalize_optional_text(slots.get("location")),
            location_latitude=None,
            location_longitude=None,
            note=_normalize_optional_text(slots.get("note")),
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


def _undo_key(team_id: uuid.UUID, user_id: uuid.UUID) -> tuple[str, str]:
    return (str(team_id), str(user_id))


def _save_undo_batch(team_id: uuid.UUID, user_id: uuid.UUID, actions: list[dict]) -> None:
    if actions:
        _UNDO_BATCHES[_undo_key(team_id, user_id)] = actions


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
            reply=_slot_prompt(current["intent"], slot_name, locale),
            status=STATUS_COLLECTING,
            intent=current["intent"],
            session_id=session_id,
            missing_slots=missing,
            pending_action=state,
            data={"requires_confirmation": state.get("requires_confirmation", False), "can_undo": False},
        )

    if state.get("requires_confirmation"):
        state["status"] = STATUS_AWAITING_CONFIRMATION
        save_session(session_id, state)
        return _build_response(
            reply=_build_confirmation_reply(steps, locale),
            status=STATUS_AWAITING_CONFIRMATION,
            intent=steps[-1]["intent"] if steps else None,
            session_id=session_id,
            pending_action=state,
            data={"requires_confirmation": True, "can_undo": False},
        )

    clear_session(session_id)
    return _execute_planned_steps(db, team_id=team_id, user_id=user_id, steps=steps, locale=locale)


def _initial_plan_response(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, message: str, locale: str) -> dict:
    intents, need_split = _plan_intents(message)
    if need_split:
        return _build_response(reply=translate(locale, "assistant.too_many_steps", count=MAX_PLAN_STEPS), status=STATUS_UNSUPPORTED, intent=INTENT_UNSUPPORTED, session_id=None, data={"can_undo": False})

    steps = _make_initial_steps(intents, message, locale)
    if not steps:
        return _build_response(reply=translate(locale, "assistant.unsupported"), status=STATUS_UNSUPPORTED, intent=INTENT_UNSUPPORTED, session_id=None, data={"can_undo": False})
    if len(steps) > MAX_PLAN_STEPS:
        return _build_response(reply=translate(locale, "assistant.too_many_steps", count=len(steps)), status=STATUS_UNSUPPORTED, intent=INTENT_UNSUPPORTED, session_id=None, data={"can_undo": False})

    state = {"status": STATUS_COLLECTING, "steps": steps, "current_step_index": 0, "requires_confirmation": _has_mutating_step(steps)}
    sid = create_session(state)
    return _collect_or_prepare(db, team_id=team_id, user_id=user_id, locale=locale, session_id=sid, state=state, incoming_message=None)


def execute_assistant(
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

        if state.get("status") == STATUS_AWAITING_CONFIRMATION:
            if _equals_any(text, TERM_SETS["yes"]):
                clear_session(session_id)
                return _execute_planned_steps(db, team_id=team_id, user_id=user_id, steps=steps, locale=locale)
            return _build_response(
                reply=translate(locale, "assistant.batch_confirm_hint"),
                status=STATUS_AWAITING_CONFIRMATION,
                intent=current_intent,
                session_id=session_id,
                pending_action=state,
                data={"requires_confirmation": True, "can_undo": False},
            )

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


def undo_last_assistant_batch(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    locale: str = "zh-CN",
) -> dict:
    locale = normalize_locale(locale)
    actions = _UNDO_BATCHES.pop(_undo_key(team_id, user_id), None)
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
