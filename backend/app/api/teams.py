from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.team import create_team, list_teams_for_user
from app.schemas.team import TeamCreate, TeamOut

router = APIRouter()


@router.get("")
def list_teams(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[TeamOut]:
    teams = list_teams_for_user(db, current_user.id)
    return [TeamOut.model_validate(t, from_attributes=True) for t in teams]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_team_route(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TeamOut:
    if not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Team name required")
    team = create_team(db, name=payload.name.strip(), owner_id=current_user.id)
    return TeamOut.model_validate(team, from_attributes=True)
