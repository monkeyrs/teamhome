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


def _has_schedule_time_hint(text: str) -> bool:
    if _CLOCK_RE.search(text):
        return True
    markers = set(PARSER_DATA["schedule_time_markers"])
    for terms in RELATIVE_DAY_TERMS.values():
        markers.update(terms)
    return _contains_term(text, markers)


def _parse_schedule_datetime(text: str) -> dt.datetime | None:
    settings = {"RELATIVE_BASE": _now_local(), "PREFER_DATES_FROM": "future"}
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


def _infer_relative_schedule_start(text: str) -> dt.datetime | None:
    base = _now_local().replace(minute=0, second=0, microsecond=0)

    day_offset = 0
    if _contains_term(text, RELATIVE_DAY_TERMS["day_after_tomorrow"]):
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


def parse_finance_text(text: str, *, use_llm: bool = True) -> dict:
    text = (text or "").strip()
    if not text:
        return {"amount": None, "type": None, "category": None}

    amount = _extract_amount(text)
    record_type = _guess_finance_type(text)
    category = _guess_finance_category(text)

    if amount is not None and amount < 0:
        amount = abs(amount)
        record_type = "expense" if record_type == "income" else "income"

    if amount is not None:
        return {"amount": amount, "type": record_type, "category": category}

    if not use_llm:
        return {"amount": None, "type": record_type, "category": category}

    client = get_llm_client()
    if not client:
        return {"amount": None, "type": record_type, "category": category}

    system = (
        "Extract finance fields from user text.\n"
        "Always reason and classify in English.\n"
        "Return JSON only with fields: amount(number|null), type(income|expense|null), category(string|null)."
    )
    try:
        data = client.chat_json(system=system, user=text) or {}
    except Exception:
        return {"amount": None, "type": record_type, "category": category}

    return {
        "amount": data.get("amount"),
        "type": data.get("type") or record_type,
        "category": data.get("category") or category,
    }


def parse_schedule_text(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"title": None, "start_time": None, "end_time": None}

    if not _has_schedule_time_hint(text):
        return {"title": text, "start_time": None, "end_time": None}

    start = _parse_schedule_datetime(text) or _infer_relative_schedule_start(text)

    title = text
    if start:
        for pattern in PARSER_DATA["schedule_title_patterns"][:-1]:
            title = re.sub(pattern, "", title)
        title = re.sub(PARSER_DATA["schedule_title_patterns"][-1], " ", title).strip()

    end: dt.datetime | None = None
    duration = _SCHEDULE_DURATION_RE.search(text)
    if start and duration:
        value = float(duration.group(1))
        unit = duration.group(2).lower()
        if PARSER_DATA["schedule_hour_unit"] in unit or unit == "h":
            end = start + dt.timedelta(hours=value)
        else:
            end = start + dt.timedelta(minutes=value)

    if not title:
        title = PARSER_DATA["schedule_default_title"]

    return {
        "title": title,
        "start_time": _iso_no_seconds(start) if start else None,
        "end_time": _iso_no_seconds(end) if end else None,
    }
