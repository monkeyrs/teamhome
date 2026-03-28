import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.schemas.team import TeamCreate, TeamDiscoverOut, TeamOut, normalize_team_name

TEAM_MEMBER_LIMIT = 30

router = APIRouter()


def serialize_team(team) -> TeamOut:
    members = getattr(team, "members", None) or []
    return TeamOut(
        id=team.id,
        name=team.name,
        owner_id=team.owner_id,
        join_password=team.join_password,
        member_count=len(members),
    )


@router.get("")
def list_teams(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[TeamOut]:
    teams = list_teams_for_user(db, current_user.id)
    return [serialize_team(t) for t in teams]


@router.get("/discover")
def discover_team(
    name: str = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TeamDiscoverOut:
    try:
        normalized_name = normalize_team_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    team = get_team_by_name(db, name=normalized_name)
    if not team:
        return TeamDiscoverOut(
            name=normalized_name,
            exists=False,
            already_joined=False,
            requires_password=False,
            member_count=0,
            team_full=False,
        )

    membership = get_team_member(db, team_id=team.id, user_id=current_user.id)
    member_count = len(getattr(team, "members", None) or [])
    return TeamDiscoverOut(
        name=normalized_name,
        exists=True,
        already_joined=membership is not None,
        requires_password=bool(team.join_password),
        member_count=member_count,
        team_full=member_count >= TEAM_MEMBER_LIMIT and membership is None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_team_route(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TeamOut:
    existing = get_team_by_name(db, name=payload.name)
    if existing:
        membership = get_team_member(db, team_id=existing.id, user_id=current_user.id)
        if membership:
            return serialize_team(existing)

        member_count = len(getattr(existing, "members", None) or [])
        if member_count >= TEAM_MEMBER_LIMIT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TEAM_MEMBER_LIMIT_REACHED")
        if existing.join_password:
            if not payload.password:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_PASSWORD_REQUIRED")
            if payload.password != existing.join_password:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_PASSWORD_INVALID")

        add_team_member(db, team_id=existing.id, user_id=current_user.id)
        refreshed = get_team_by_name(db, name=payload.name)
        return serialize_team(refreshed or existing)

    team = create_team(db, name=payload.name, owner_id=current_user.id, join_password=payload.password)
    refreshed = get_team_by_name(db, name=payload.name)
    return serialize_team(refreshed or team)


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
