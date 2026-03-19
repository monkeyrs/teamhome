import uuid

from sqlalchemy.orm import Session

from app.crud.finance import create_finance_record
from app.schemas.finance import FinanceCreate


def create_finance_from_schema(db: Session, *, payload: FinanceCreate, user_id: uuid.UUID):
    return create_finance_record(
        db,
        team_id=payload.team_id,
        user_id=user_id,
        amount=payload.amount,
        record_type=payload.type,
        category=payload.category,
        location=payload.location,
        note=payload.note,
    )
