import uuid

from sqlalchemy.orm import Session

from app.crud.schedule import create_schedule
from app.schemas.schedule import ScheduleCreate


def create_schedule_from_schema(
    db: Session, *, payload: ScheduleCreate, created_by: uuid.UUID
):
    return create_schedule(
        db,
        team_id=payload.team_id,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        is_all_day=payload.is_all_day,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=created_by,
    )
