import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.team import (
    add_team_member,
    create_team,
    get_team_by_name,
    get_team_member,
    list_teams_for_user,
    remove_team_member,
)
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
    existing = get_team_by_name(db, name=payload.name)
    if existing:
        membership = get_team_member(db, team_id=existing.id, user_id=current_user.id)
        if not membership:
            add_team_member(db, team_id=existing.id, user_id=current_user.id)
        return TeamOut.model_validate(existing, from_attributes=True)

    team = create_team(db, name=payload.name, owner_id=current_user.id)
    return TeamOut.model_validate(team, from_attributes=True)


@router.delete("/{team_id}/members/me", status_code=status.HTTP_204_NO_CONTENT)
def leave_team_route(
    team_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> None:
    membership = get_team_member(db, team_id=uuid.UUID(team_id), user_id=current_user.id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team membership not found")
    remove_team_member(db, membership=membership)
