import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.schedule import create_schedule, list_schedules
from app.crud.team import is_team_member
from app.schemas.schedule import ScheduleCreate, ScheduleOut, ScheduleParseIn, ScheduleParseOut
from app.services.llm.parser import parse_schedule_text

router = APIRouter()


@router.get("")
def list_schedules_route(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[ScheduleOut]:
    if not is_team_member(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    items = list_schedules(db, team_id=team_id)
    return [ScheduleOut.model_validate(s, from_attributes=True) for s in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule_route(
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ScheduleOut:
    if not is_team_member(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    schedule = create_schedule(
        db,
        team_id=payload.team_id,
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=current_user.id,
    )
    return ScheduleOut.model_validate(schedule, from_attributes=True)


@router.post("/parse")
def parse_schedule(payload: ScheduleParseIn) -> ScheduleParseOut:
    data = parse_schedule_text(payload.text)
    return ScheduleParseOut(**data)
