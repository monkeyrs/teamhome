import uuid

import decimal

from sqlalchemy.orm import Session

from app.models.finance import FinanceRecord


def create_finance_record(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: decimal.Decimal,
    record_type: str,
    category: str,
    note: str | None,
) -> FinanceRecord:
    record = FinanceRecord(
        team_id=team_id,
        user_id=user_id,
        amount=amount,
        type=record_type,
        category=category,
        note=note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_finance_records(db: Session, *, team_id: uuid.UUID) -> list[FinanceRecord]:
    return (
        db.query(FinanceRecord)
        .filter(FinanceRecord.team_id == team_id)
        .order_by(FinanceRecord.created_at.desc())
        .all()
    )
