import decimal
import datetime as dt
import uuid

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
        location=location,
        location_latitude=location_latitude,
        location_longitude=location_longitude,
        note=note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_finance_records(db: Session, *, team_id: uuid.UUID) -> list[FinanceRecord]:
    return (
        db.query(FinanceRecord)
        .filter(FinanceRecord.team_id == team_id, FinanceRecord.deleted_at.is_(None))
        .order_by(FinanceRecord.created_at.desc())
        .all()
    )


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
    location: str | None,
    location_latitude: float | None,
    location_longitude: float | None,
    note: str | None,
) -> FinanceRecord:
    record.amount = amount
    record.type = record_type
    record.category = category
    record.location = location
    record.location_latitude = location_latitude
    record.location_longitude = location_longitude
    record.note = note
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
