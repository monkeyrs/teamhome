import decimal
import datetime as dt
import uuid

from sqlalchemy import func
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
    occurred_at: dt.datetime | None,
    location: str | None,
    location_latitude: float | None,
    location_longitude: float | None,
    note: str | None,
) -> FinanceRecord:
    record = FinanceRecord(
        team_id=team_id,
        user_id=user_id,
        amount=amount,
        type=record_type,
        category=category,
        occurred_at=occurred_at or dt.datetime.now(dt.timezone.utc),
        location=location,
        location_latitude=location_latitude,
        location_longitude=location_longitude,
        note=note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_finance_records(
    db: Session,
    *,
    team_id: uuid.UUID,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> list[FinanceRecord]:
    query = db.query(FinanceRecord).filter(FinanceRecord.team_id == team_id, FinanceRecord.deleted_at.is_(None))
    if window_start is not None:
        query = query.filter(FinanceRecord.occurred_at > window_start)
    if window_end is not None:
        query = query.filter(FinanceRecord.occurred_at <= window_end)
    return query.order_by(FinanceRecord.occurred_at.desc(), FinanceRecord.created_at.desc()).all()


def get_finance_record(db: Session, *, record_id: uuid.UUID) -> FinanceRecord | None:
    return db.query(FinanceRecord).filter(FinanceRecord.id == record_id).first()


def soft_delete_finance_record(db: Session, *, record: FinanceRecord, batch_id: uuid.UUID) -> None:
    record.deleted_at = dt.datetime.now(dt.timezone.utc)
    record.deleted_batch_id = batch_id
    db.add(record)
    db.commit()


def update_finance_record(
    db: Session,
    *,
    record: FinanceRecord,
    amount: decimal.Decimal,
    record_type: str,
    category: str,
    occurred_at: dt.datetime | None,
    location: str | None,
    location_latitude: float | None,
    location_longitude: float | None,
    note: str | None,
) -> FinanceRecord:
    record.amount = amount
    record.type = record_type
    record.category = category
    record.occurred_at = occurred_at or record.occurred_at or dt.datetime.now(dt.timezone.utc)
    record.location = location
    record.location_latitude = location_latitude
    record.location_longitude = location_longitude
    record.note = note
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_popular_categories(db: Session, *, team_id: uuid.UUID, limit: int = 5) -> list[str]:
    rows = (
        db.query(FinanceRecord.category, func.count(FinanceRecord.id).label("total"))
        .filter(
            FinanceRecord.team_id == team_id,
            FinanceRecord.deleted_at.is_(None),
            FinanceRecord.category.is_not(None),
            FinanceRecord.category != "",
        )
        .group_by(FinanceRecord.category)
        .order_by(func.count(FinanceRecord.id).desc(), FinanceRecord.category.asc())
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows if row[0]]
