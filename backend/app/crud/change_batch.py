import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.models.change_batch import ChangeBatch
from app.models.finance import FinanceRecord
from app.models.schedule import Schedule


def create_change_batch(
    db: Session,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    entity_type: str,
) -> ChangeBatch:
    batch = ChangeBatch(team_id=team_id, user_id=user_id, action=action, entity_type=entity_type)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def list_recent_batches(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, limit: int = 3) -> list[ChangeBatch]:
    return (
        db.query(ChangeBatch)
        .filter(ChangeBatch.team_id == team_id, ChangeBatch.user_id == user_id, ChangeBatch.action == "delete")
        .order_by(ChangeBatch.created_at.desc())
        .limit(limit)
        .all()
    )


def get_last_batch(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> ChangeBatch | None:
    return (
        db.query(ChangeBatch)
        .filter(ChangeBatch.team_id == team_id, ChangeBatch.user_id == user_id, ChangeBatch.action == "delete")
        .order_by(ChangeBatch.created_at.desc())
        .first()
    )


def prune_old_batches(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, keep: int = 3) -> None:
    batches = (
        db.query(ChangeBatch)
        .filter(ChangeBatch.team_id == team_id, ChangeBatch.user_id == user_id, ChangeBatch.action == "delete")
        .order_by(ChangeBatch.created_at.desc())
        .all()
    )
    for batch in batches[keep:]:
        db.query(Schedule).filter(Schedule.deleted_batch_id == batch.id).delete(synchronize_session=False)
        db.query(FinanceRecord).filter(FinanceRecord.deleted_batch_id == batch.id).delete(synchronize_session=False)
        db.delete(batch)
    db.commit()


def restore_batch(db: Session, *, batch: ChangeBatch) -> None:
    db.query(Schedule).filter(Schedule.deleted_batch_id == batch.id).update(
        {"deleted_at": None, "deleted_batch_id": None}, synchronize_session=False
    )
    db.query(FinanceRecord).filter(FinanceRecord.deleted_batch_id == batch.id).update(
        {"deleted_at": None, "deleted_batch_id": None}, synchronize_session=False
    )
    db.delete(batch)
    db.commit()
