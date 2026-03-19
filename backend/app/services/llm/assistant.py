from __future__ import annotations

import datetime as dt
import re
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.finance import FinanceRecord


def _month_range(base: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    first = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_end = first - dt.timedelta(seconds=1)
    prev_first = prev_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return prev_first, first


def answer_finance_question(db: Session, *, team_id: uuid.UUID, question: str) -> dict:
    q = (question or "").strip()
    if not q:
        return {"answer": "问题为空", "data": None}

    if "上个月" in q and ("餐饮" in q or "吃" in q or "饭" in q):
        start, end = _month_range(dt.datetime.now().astimezone())
        total = (
            db.query(func.coalesce(func.sum(FinanceRecord.amount), 0))
            .filter(
                FinanceRecord.team_id == team_id,
                FinanceRecord.type == "expense",
                FinanceRecord.created_at >= start,
                FinanceRecord.created_at < end,
                FinanceRecord.category.in_(["food", "餐饮", "food"]),
            )
            .scalar()
        )
        return {"answer": f"上个月餐饮支出合计 {total}", "data": {"total": str(total), "start": start.isoformat(), "end": end.isoformat()}}

    if re.search(r"总(共)?花(了)?多少", q):
        total = (
            db.query(func.coalesce(func.sum(FinanceRecord.amount), 0))
            .filter(FinanceRecord.team_id == team_id, FinanceRecord.type == "expense")
            .scalar()
        )
        return {"answer": f"当前总支出 {total}", "data": {"total": str(total)}}

    return {"answer": "暂不支持该问题（可先按分类/时间段查询）", "data": None}
