import datetime as dt
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.schedule import Schedule


def create_schedule(
    db: Session,
    *,
    team_id: uuid.UUID,
    title: str,
    description: str | None,
    location: str | None,
    location_latitude: float | None,
    location_longitude: float | None,
    is_all_day: bool,
    start_time: dt.datetime,
    end_time: dt.datetime | None,
    created_by: uuid.UUID,
) -> Schedule:
    schedule = Schedule(
        team_id=team_id,
        title=title,
        description=description,
        location=location,
        location_latitude=location_latitude,
        location_longitude=location_longitude,
        is_all_day=is_all_day,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def list_schedules(
    db: Session,
    *,
    team_id: uuid.UUID,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> list[Schedule]:
    query = db.query(Schedule).filter(Schedule.team_id == team_id, Schedule.deleted_at.is_(None))
    if window_start is not None:
        query = query.filter(Schedule.start_time > window_start)
    if window_end is not None:
        query = query.filter(Schedule.start_time <= window_end)
    return query.order_by(Schedule.start_time.desc(), Schedule.created_at.desc()).all()


def list_schedule_conflicts(
    db: Session,
    *,
    team_id: uuid.UUID,
    start_time: dt.datetime,
    end_time: dt.datetime,
    exclude_schedule_id: uuid.UUID | None = None,
) -> list[Schedule]:
    query = db.query(Schedule).filter(
        Schedule.team_id == team_id,
        Schedule.deleted_at.is_(None),
        Schedule.start_time < end_time,
        or_(Schedule.end_time.is_(None), Schedule.end_time > start_time),
    )
    if exclude_schedule_id:
        query = query.filter(Schedule.id != exclude_schedule_id)
    return query.order_by(Schedule.start_time.asc()).all()


def get_schedule(db: Session, *, schedule_id: uuid.UUID) -> Schedule | None:
    return db.query(Schedule).filter(Schedule.id == schedule_id).first()


def soft_delete_schedule(db: Session, *, schedule: Schedule, batch_id: uuid.UUID) -> None:
    schedule.deleted_at = dt.datetime.now(dt.timezone.utc)
    schedule.deleted_batch_id = batch_id
    db.add(schedule)
    db.commit()


def update_schedule(
    db: Session,
    *,
    schedule: Schedule,
    title: str,
    description: str | None,
    location: str | None,
    location_latitude: float | None,
    location_longitude: float | None,
    is_all_day: bool,
    start_time: dt.datetime,
    end_time: dt.datetime | None,
    status: str | None = None,
) -> Schedule:
    schedule.title = title
    schedule.description = description
    schedule.location = location
    schedule.location_latitude = location_latitude
    schedule.location_longitude = location_longitude
    schedule.is_all_day = is_all_day
    schedule.start_time = start_time
    schedule.end_time = end_time
    if status is not None:
        schedule.status = status
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule
