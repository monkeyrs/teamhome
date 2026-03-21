import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.crud.finance import create_finance_record
from app.schemas.finance import FinanceCreate


def create_finance_from_schema(db: Session, *, payload: FinanceCreate, user_id: uuid.UUID):
    occurred_at = None
    if payload.occurred_at:
        normalized = payload.occurred_at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        occurred_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return create_finance_record(
        db,
        team_id=payload.team_id,
        user_id=user_id,
        amount=payload.amount,
        record_type=payload.type,
        category=payload.category,
        occurred_at=occurred_at,
        location=payload.location,
        location_latitude=payload.location_latitude,
        location_longitude=payload.location_longitude,
        note=payload.note,
    )
