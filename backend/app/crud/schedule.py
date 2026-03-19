import uuid

import datetime as dt

from sqlalchemy.orm import Session

from app.models.schedule import Schedule


def create_schedule(
    db: Session,
    *,
    team_id: uuid.UUID,
    title: str,
    description: str | None,
    start_time: dt.datetime,
    end_time: dt.datetime | None,
    created_by: uuid.UUID,
) -> Schedule:
    schedule = Schedule(
        team_id=team_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def list_schedules(db: Session, *, team_id: uuid.UUID) -> list[Schedule]:
    return (
        db.query(Schedule)
        .filter(Schedule.team_id == team_id)
        .order_by(Schedule.start_time.asc())
        .all()
    )
