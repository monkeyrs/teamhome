from __future__ import annotations

import datetime as dt
import re

import dateparser

from app.core.i18n import PARSER_DATA, RELATIVE_DAY_TERMS
from app.services.llm.openrouter import get_llm_client


_AMOUNT_RE = re.compile(PARSER_DATA["amount_pattern"])
_BARE_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_SCHEDULE_DURATION_RE = re.compile(PARSER_DATA["schedule_duration_pattern"])
_CLOCK_RE = re.compile(PARSER_DATA["schedule_clock_pattern"], re.IGNORECASE)


def _guess_finance_type(text: str) -> str:
    lowered = text.casefold()
    if any(word.casefold() in lowered for word in PARSER_DATA["finance_income_words"]):
        return "income"
    if any(word.casefold() in lowered for word in PARSER_DATA["finance_expense_words"]):
        return "expense"
    return "expense"


def _has_income_hint(text: str) -> bool:
    lowered = text.casefold()
    return any(word.casefold() in lowered for word in PARSER_DATA["finance_income_words"])


def _has_expense_hint(text: str) -> bool:
    lowered = text.casefold()
    return any(word.casefold() in lowered for word in PARSER_DATA["finance_expense_words"])


def _infer_finance_type_with_llm(text: str, fallback: str) -> str:
    client = get_llm_client()
    if not client:
        return fallback
    system = (
        "Classify finance record type from user text.\n"
        "Always reason in English.\n"
        "Return JSON only: {\"type\":\"income\"} or {\"type\":\"expense\"}."
    )
    try:
        data = client.chat_json(system=system, user=text) or {}
    except Exception:
        return fallback
    record_type = str(data.get("type") or "").strip().lower()
    return record_type if record_type in {"income", "expense"} else fallback


def _resolve_finance_type(text: str, *, use_llm: bool) -> tuple[str, str]:
    has_income_hint = _has_income_hint(text)
    has_expense_hint = _has_expense_hint(text)

    if has_income_hint and not has_expense_hint:
        return "income", "high"
    if has_expense_hint and not has_income_hint:
        return "expense", "high"

    fallback = _guess_finance_type(text)
    if not use_llm:
        return fallback, "low"
    resolved = _infer_finance_type_with_llm(text, fallback)
    return resolved, "low"


def _guess_finance_category(text: str) -> str:
    lowered = text.casefold()
    for keyword, category in PARSER_DATA["finance_category_mapping"]:
        if keyword.casefold() in lowered:
            return category
    return "other"


def _extract_amount(text: str) -> float | None:
    matches = _AMOUNT_RE.findall(text)
    if matches:
        last = matches[-1]
        amount_text = last[0] if isinstance(last, tuple) else last
        try:
            return float(amount_text)
        except ValueError:
            return None

    lowered = text.casefold()
    has_finance_verb = any(
        word.casefold() in lowered
        for word in (PARSER_DATA["finance_income_words"] + PARSER_DATA["finance_expense_words"])
    )
    if not has_finance_verb:
        return None

    numbers = _BARE_NUMBER_RE.findall(text)
    if not numbers:
        return None
    try:
        return float(numbers[-1])
    except ValueError:
        return None


def _now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _iso_no_seconds(value: dt.datetime) -> str:
    return value.replace(second=0, microsecond=0).isoformat()


def _contains_term(text: str, terms: set[str]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _relative_day_offset(text: str) -> int | None:
    if _contains_term(text, RELATIVE_DAY_TERMS["day_after_tomorrow"]):
        return 2
    if _contains_term(text, RELATIVE_DAY_TERMS["tomorrow"]):
        return 1
    if _contains_term(text, RELATIVE_DAY_TERMS["yesterday"]):
        return -1
    if _contains_term(text, RELATIVE_DAY_TERMS["today"]):
        return 0
    return None


def _apply_relative_day(value: dt.datetime | None, text: str) -> dt.datetime | None:
    if value is None:
        return None
    offset = _relative_day_offset(text)
    if offset is None:
        return value
    base = _now_local() + dt.timedelta(days=offset)
    normalized = value.astimezone(base.tzinfo) if value.tzinfo else value.replace(tzinfo=base.tzinfo)
    return normalized.replace(year=base.year, month=base.month, day=base.day)


def _has_schedule_time_hint(text: str) -> bool:
    if _CLOCK_RE.search(text):
        return True
    markers = set(PARSER_DATA["schedule_time_markers"])
    for terms in RELATIVE_DAY_TERMS.values():
        markers.update(terms)
    return _contains_term(text, markers)


def _parse_datetime(text: str, *, prefer_dates_from: str) -> dt.datetime | None:
    settings = {"RELATIVE_BASE": _now_local(), "PREFER_DATES_FROM": prefer_dates_from}
    language_candidates: list[list[str] | None] = [["zh", "en", "ja"], ["zh"], ["en"], ["ja"], None]
    for languages in language_candidates:
        try:
            if languages:
                parsed = dateparser.parse(text, languages=languages, settings=settings)
            else:
                parsed = dateparser.parse(text, settings=settings)
        except Exception:
            parsed = None
        if parsed:
            return parsed
    return None


def _parse_schedule_datetime(text: str) -> dt.datetime | None:
    prefer_dates_from = "future"
    if _contains_term(text, RELATIVE_DAY_TERMS["yesterday"]):
        prefer_dates_from = "past"
    return _parse_datetime(text, prefer_dates_from=prefer_dates_from)


def _infer_finance_default_hour(text: str, category: str | None) -> int | None:
    for profile in PARSER_DATA["finance_time_profiles"]:
        terms = set(profile.get("terms") or [])
        if _contains_term(text, terms):
            return int(profile.get("hour"))
    if category == "food":
        return int(PARSER_DATA["finance_food_default_hour"])
    if (
        _contains_term(text, RELATIVE_DAY_TERMS["yesterday"])
        or _contains_term(text, RELATIVE_DAY_TERMS["today"])
        or _contains_term(text, RELATIVE_DAY_TERMS["tomorrow"])
    ):
        return int(PARSER_DATA["finance_relative_default_hour"])
    return None


def _infer_finance_occurred_at(text: str, category: str | None) -> dt.datetime | None:
    base = _now_local()
    parsed = _parse_datetime(text, prefer_dates_from="past")

    if not parsed:
        if _contains_term(text, RELATIVE_DAY_TERMS["yesterday"]):
            parsed = base - dt.timedelta(days=1)
        elif _contains_term(text, RELATIVE_DAY_TERMS["today"]):
            parsed = base
        elif _contains_term(text, RELATIVE_DAY_TERMS["tomorrow"]):
            parsed = base + dt.timedelta(days=1)
        else:
            parsed = base

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=base.tzinfo)
    parsed = _apply_relative_day(parsed, text)

    if not _CLOCK_RE.search(text):
        default_hour = _infer_finance_default_hour(text, category)
        if default_hour is not None:
            parsed = parsed.replace(hour=default_hour, minute=0, second=0, microsecond=0)
        else:
            parsed = parsed.replace(second=0, microsecond=0)
    else:
        parsed = parsed.replace(second=0, microsecond=0)
    return parsed


def _infer_relative_schedule_start(text: str) -> dt.datetime | None:
    base = _now_local().replace(minute=0, second=0, microsecond=0)

    day_offset = 0
    if _contains_term(text, RELATIVE_DAY_TERMS["yesterday"]):
        day_offset = -1
    elif _contains_term(text, RELATIVE_DAY_TERMS["day_after_tomorrow"]):
        day_offset = 2
    elif _contains_term(text, RELATIVE_DAY_TERMS["tomorrow"]):
        day_offset = 1

    target = base + dt.timedelta(days=day_offset)

    hour: int | None = None
    for profile in PARSER_DATA["schedule_time_profiles"]:
        terms = set(profile.get("terms") or [])
        candidate_hour = int(profile.get("hour"))
        if _contains_term(text, terms):
            hour = candidate_hour
            break

    if hour is None:
        if _contains_term(text, RELATIVE_DAY_TERMS["today"]):
            hour = max(base.hour + 1, 9)
        elif day_offset > 0:
            hour = 9
        else:
            return None

    return target.replace(hour=hour)


def _clean_schedule_title(text: str) -> str:
    title = text or ""
    for pattern in PARSER_DATA["schedule_title_patterns"][:-1]:
        title = re.sub(pattern, "", title)
    title = re.sub(PARSER_DATA["schedule_title_patterns"][-1], " ", title).strip()
    title = re.sub(r"^(?:有|要|会|去|安排|参加)\s*", "", title)
    title = re.sub(r"^(?:我(?:们)?)(?:要|会|想|得)?\s*", "", title)
    title = re.sub(r"^(?:一下|一个|去)\s*", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _infer_schedule_default_end(text: str, start: dt.datetime | None) -> dt.datetime | None:
    if not start or _CLOCK_RE.search(text):
        return None
    if _contains_term(text, {"morning", "上午", "早上", "午前"}):
        return start + dt.timedelta(hours=2)
    if _contains_term(text, {"noon", "中午"}):
        return start + dt.timedelta(hours=1)
    if _contains_term(text, {"afternoon", "下午", "午後"}):
        return start + dt.timedelta(hours=1)
    if _contains_term(text, {"evening", "tonight", "晚上", "今晚", "夜"}):
        return start + dt.timedelta(hours=1)
    return None


def parse_finance_text(text: str, *, use_llm: bool = True) -> dict:
    text = (text or "").strip()
    if not text:
        return {"amount": None, "type": None, "type_confidence": "low", "category": None, "occurred_at": None, "note": None}

    amount = _extract_amount(text)
    record_type, type_confidence = _resolve_finance_type(text, use_llm=use_llm)
    category = _guess_finance_category(text)
    occurred_at = _infer_finance_occurred_at(text, category)

    if amount is not None and amount < 0:
        amount = abs(amount)
        record_type = "expense" if record_type == "income" else "income"
        type_confidence = "high"

    if amount is not None:
        return {
            "amount": amount,
            "type": record_type,
            "type_confidence": type_confidence,
            "category": category,
            "occurred_at": _iso_no_seconds(occurred_at) if occurred_at else None,
            "note": text,
        }

    if not use_llm:
        return {
            "amount": None,
            "type": record_type,
            "type_confidence": type_confidence,
            "category": category,
            "occurred_at": _iso_no_seconds(occurred_at) if occurred_at else None,
            "note": text,
        }

    client = get_llm_client()
    if not client:
        return {
            "amount": None,
            "type": record_type,
            "type_confidence": type_confidence,
            "category": category,
            "occurred_at": _iso_no_seconds(occurred_at) if occurred_at else None,
            "note": text,
        }

    system = (
        "Extract finance fields from user text.\n"
        "Always reason and classify in English.\n"
        "Return JSON only with fields: amount(number|null), type(income|expense|null), category(string|null), occurred_at(ISO8601|null)."
    )
    try:
        data = client.chat_json(system=system, user=text) or {}
    except Exception:
        return {
            "amount": None,
            "type": record_type,
            "type_confidence": type_confidence,
            "category": category,
            "occurred_at": _iso_no_seconds(occurred_at) if occurred_at else None,
            "note": text,
        }

    llm_type = str(data.get("type") or "").strip().lower()
    if llm_type in {"income", "expense"}:
        record_type = llm_type

    return {
        "amount": data.get("amount"),
        "type": record_type,
        "type_confidence": type_confidence,
        "category": data.get("category") or category,
        "occurred_at": data.get("occurred_at") or (_iso_no_seconds(occurred_at) if occurred_at else None),
        "note": text,
    }


def parse_schedule_text(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"title": None, "start_time": None, "end_time": None}

    if not _has_schedule_time_hint(text):
        return {"title": text, "start_time": None, "end_time": None}

    start = _apply_relative_day(_parse_schedule_datetime(text), text) or _infer_relative_schedule_start(text)

    title = _clean_schedule_title(text) if start else text

    end: dt.datetime | None = None
    duration = _SCHEDULE_DURATION_RE.search(text)
    if start and duration:
        value = float(duration.group(1))
        unit = duration.group(2).lower()
        if PARSER_DATA["schedule_hour_unit"] in unit or unit == "h":
            end = start + dt.timedelta(hours=value)
        else:
            end = start + dt.timedelta(minutes=value)
    if start and end is None:
        end = _infer_schedule_default_end(text, start)

    if not title:
        title = PARSER_DATA["schedule_default_title"]

    return {
        "title": title,
        "start_time": _iso_no_seconds(start) if start else None,
        "end_time": _iso_no_seconds(end) if end else None,
    }
