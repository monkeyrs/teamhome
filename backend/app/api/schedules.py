import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.change_batch import create_change_batch, prune_old_batches
from app.crud.place import touch_place
from app.crud.schedule import create_schedule, get_schedule, list_schedules, soft_delete_schedule, update_schedule
from app.crud.team import can_read_team, can_write_team
from app.schemas.schedule import ScheduleCreate, ScheduleOut, ScheduleParseIn, ScheduleParseOut, ScheduleUpdate
from app.services.llm.parser import parse_schedule_text

router = APIRouter()


def to_schedule_out(item) -> ScheduleOut:
    return ScheduleOut.model_validate(
        {
            "id": item.id,
            "team_id": item.team_id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "location_latitude": item.location_latitude,
            "location_longitude": item.location_longitude,
            "is_all_day": item.is_all_day,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "created_by": item.created_by,
            "creator_nickname": getattr(getattr(item, "creator", None), "nickname", None),
            "status": item.status,
            "created_at": item.created_at,
        }
    )


@router.get("")
def list_schedules_route(
    team_id: uuid.UUID,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[ScheduleOut]:
    if not can_read_team(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    items = list_schedules(db, team_id=team_id, window_start=window_start, window_end=window_end)
    return [to_schedule_out(item) for item in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule_route(
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ScheduleOut:
    if not can_read_team(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    if not can_write_team(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_READ_ONLY")
    schedule = create_schedule(
        db,
        team_id=payload.team_id,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        location_latitude=payload.location_latitude,
        location_longitude=payload.location_longitude,
        is_all_day=payload.is_all_day,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=current_user.id,
    )
    touch_place(db, team_id=payload.team_id, name=payload.location or "")
    return to_schedule_out(schedule)


@router.post("/parse")
def parse_schedule(payload: ScheduleParseIn, current_user=Depends(get_current_user)) -> ScheduleParseOut:
    data = parse_schedule_text(payload.text)
    return ScheduleParseOut(**data)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_route(
    schedule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> None:
    schedule = get_schedule(db, schedule_id=schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    if not can_read_team(db, team_id=schedule.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    if not can_write_team(db, team_id=schedule.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_READ_ONLY")
    batch = create_change_batch(db, team_id=schedule.team_id, user_id=current_user.id, action="delete", entity_type="schedule")
    soft_delete_schedule(db, schedule=schedule, batch_id=batch.id)
    prune_old_batches(db, team_id=schedule.team_id, user_id=current_user.id, keep=3)


@router.put("/{schedule_id}")
def update_schedule_route(
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ScheduleOut:
    schedule = get_schedule(db, schedule_id=schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    if not can_read_team(db, team_id=schedule.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    if not can_write_team(db, team_id=schedule.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_READ_ONLY")
    schedule = update_schedule(
        db,
        schedule=schedule,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        location_latitude=payload.location_latitude,
        location_longitude=payload.location_longitude,
        is_all_day=payload.is_all_day,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=payload.status,
    )
    touch_place(db, team_id=schedule.team_id, name=payload.location or "")
    return to_schedule_out(schedule)
