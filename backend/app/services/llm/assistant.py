from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.i18n import TERM_SETS, translate
from app.core.timezone import now_in_app_timezone
from app.models.finance import FinanceRecord
from app.services.llm.openrouter import get_llm_client


def _month_range(base: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    first = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_end = first - dt.timedelta(seconds=1)
    prev_first = prev_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return prev_first, first


def _decimal_to_str(value: decimal.Decimal | None) -> str:
    if value is None:
        return "0.00"
    return format(value.quantize(decimal.Decimal("0.01")), "f")


def _fallback_answer(
    db: Session,
    *,
    team_id: uuid.UUID,
    question: str,
    locale: str,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> dict:
    q = (question or "").strip()
    if not q:
        return {"answer": translate(locale, "finance.empty_question"), "data": None}

    lower_q = q.casefold()
    if any(term.casefold() in lower_q for term in TERM_SETS["last_month_terms"]) and any(
        term.casefold() in lower_q for term in TERM_SETS["food_terms"]
    ):
        start, end = _month_range(now_in_app_timezone())
        total = (
            db.query(func.coalesce(func.sum(FinanceRecord.amount), 0))
            .filter(
                FinanceRecord.team_id == team_id,
                FinanceRecord.deleted_at.is_(None),
                FinanceRecord.type == "expense",
                FinanceRecord.occurred_at >= start,
                FinanceRecord.occurred_at < end,
                FinanceRecord.category.in_(list(TERM_SETS["food_categories"])),
            )
            .scalar()
        )
        return {
            "answer": translate(locale, "finance.last_month_food", total=_decimal_to_str(total)),
            "data": {"total": _decimal_to_str(total), "start": start.isoformat(), "end": end.isoformat()},
        }

    total_query = db.query(func.coalesce(func.sum(FinanceRecord.amount), 0)).filter(
        FinanceRecord.team_id == team_id,
        FinanceRecord.deleted_at.is_(None),
        FinanceRecord.type == "expense",
    )
    if window_start is not None:
        total_query = total_query.filter(FinanceRecord.occurred_at > window_start)
    if window_end is not None:
        total_query = total_query.filter(FinanceRecord.occurred_at <= window_end)
    total = total_query.scalar()
    return {
        "answer": translate(locale, "finance.total_expense", total=_decimal_to_str(total)),
        "data": {"total_expense": _decimal_to_str(total)},
    }


def _build_finance_snapshot(
    db: Session,
    *,
    team_id: uuid.UUID,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> dict:
    query = db.query(FinanceRecord).filter(FinanceRecord.team_id == team_id, FinanceRecord.deleted_at.is_(None))
    if window_start is not None:
        query = query.filter(FinanceRecord.occurred_at > window_start)
    if window_end is not None:
        query = query.filter(FinanceRecord.occurred_at <= window_end)
    records = query.order_by(FinanceRecord.occurred_at.desc(), FinanceRecord.created_at.desc()).limit(50).all()

    total_expense = decimal.Decimal("0")
    total_income = decimal.Decimal("0")
    by_category: dict[str, decimal.Decimal] = {}
    recent_items: list[dict] = []

    for item in records:
        amount = item.amount or decimal.Decimal("0")
        if item.type == "income":
            total_income += amount
        else:
            total_expense += amount
            key = item.category or "other"
            by_category[key] = by_category.get(key, decimal.Decimal("0")) + amount

        recent_items.append(
            {
                "amount": _decimal_to_str(amount),
                "type": item.type,
                "category": item.category,
                "location": item.location,
                "note": item.note,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    top_categories = sorted(by_category.items(), key=lambda pair: pair[1], reverse=True)[:8]
    return {
        "record_count": len(records),
        "total_expense": _decimal_to_str(total_expense),
        "total_income": _decimal_to_str(total_income),
        "top_expense_categories": [
            {"category": category, "amount": _decimal_to_str(amount)} for category, amount in top_categories
        ],
        "recent_records": recent_items[:20],
    }


def answer_finance_question(
    db: Session,
    *,
    team_id: uuid.UUID,
    question: str,
    locale: str = "zh-CN",
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> dict:
    q = (question or "").strip()
    if not q:
        return {"answer": translate(locale, "finance.empty_question"), "data": None}

    snapshot = _build_finance_snapshot(db, team_id=team_id, window_start=window_start, window_end=window_end)
    client = get_llm_client()
    if not client:
        return _fallback_answer(
            db,
            team_id=team_id,
            question=q,
            locale=locale,
            window_start=window_start,
            window_end=window_end,
        )

    response_language = {
        "zh-CN": "Simplified Chinese",
        "en-US": "English",
        "ja-JP": "Japanese",
    }.get(locale, "Simplified Chinese")
    system_prompt = (
        "You are a team finance assistant.\n"
        "Always reason, compute, and judge in English.\n"
        "Answer only from the finance snapshot provided by the user.\n"
        "Do not invent numbers or records.\n"
        f"Write the final `answer` field in {response_language}.\n"
        "If the snapshot is insufficient, say what is missing.\n"
        "Return valid JSON only."
    )
    user_prompt = (
        f"User locale: {locale}\n"
        f"User question: {q}\n\n"
        f"Finance snapshot: {snapshot}\n\n"
        'Return a JSON object with two fields:\n'
        '1) "answer": final user-facing answer string.\n'
        '2) "data": key numeric facts referenced; null if none.\n'
        "Do not output anything outside JSON."
    )

    try:
        result = client.chat_json(system=system_prompt, user=user_prompt) or {}
    except Exception:
        return _fallback_answer(
            db,
            team_id=team_id,
            question=q,
            locale=locale,
            window_start=window_start,
            window_end=window_end,
        )

    answer = str(result.get("answer") or "").strip()
    if not answer:
        return _fallback_answer(
            db,
            team_id=team_id,
            question=q,
            locale=locale,
            window_start=window_start,
            window_end=window_end,
        )

    data = result.get("data")
    if data is not None and not isinstance(data, dict):
        data = {"value": data}
    return {"answer": answer, "data": data}
