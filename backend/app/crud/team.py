import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.team import DemoTeamHide, Team, TeamMember

DEMO_TEAM_ORDER = {
    "Badz乐队": 0,
    "teamhome开发": 1,
}


def create_team(
    db: Session,
    *,
    name: str,
    owner_id: uuid.UUID,
    join_password: str | None = None,
    is_demo: bool = False,
) -> Team:
    team = Team(name=name, owner_id=owner_id, join_password=join_password, is_demo=is_demo)
    db.add(team)
    db.commit()
    db.refresh(team)

    membership = TeamMember(team_id=team.id, user_id=owner_id, role="admin")
    db.add(membership)
    db.commit()
    return team


def get_team_by_name(db: Session, *, name: str) -> Team | None:
    return (
        db.query(Team)
        .options(joinedload(Team.members), joinedload(Team.hidden_by_users))
        .filter(Team.name == name)
        .first()
    )


def add_team_member(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, role: str = "member") -> TeamMember:
    membership = TeamMember(team_id=team_id, user_id=user_id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def get_team(db: Session, team_id: uuid.UUID) -> Team | None:
    return (
        db.query(Team)
        .options(joinedload(Team.members), joinedload(Team.hidden_by_users))
        .filter(Team.id == team_id)
        .first()
    )


def list_teams_for_user(db: Session, user_id: uuid.UUID) -> list[Team]:
    return (
        db.query(Team)
        .options(joinedload(Team.members))
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == user_id)
        .order_by(Team.created_at.desc())
        .all()
    )


def list_accessible_teams_for_user(db: Session, user_id: uuid.UUID) -> list[Team]:
    member_teams = list_teams_for_user(db, user_id=user_id)
    hidden_demo_team_ids = {
        item.team_id
        for item in db.query(DemoTeamHide).filter(DemoTeamHide.user_id == user_id).all()
    }
    demo_teams = (
        db.query(Team)
        .options(joinedload(Team.members), joinedload(Team.hidden_by_users))
        .filter(Team.is_demo.is_(True))
        .all()
    )
    visible_demo_teams = [team for team in demo_teams if team.id not in hidden_demo_team_ids]
    visible_demo_teams.sort(key=lambda item: (DEMO_TEAM_ORDER.get(item.name, 999), item.name))
    return member_teams + visible_demo_teams


def count_team_members(db: Session, *, team_id: uuid.UUID) -> int:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id).count()


def is_team_member(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
        is not None
    )


def get_team_members(db: Session, *, team_id: uuid.UUID) -> list[TeamMember]:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id).all()


def get_team_member(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMember | None:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()


def remove_team_member(db: Session, *, membership: TeamMember) -> None:
    db.delete(membership)
    db.commit()


def is_demo_team_hidden(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.query(DemoTeamHide)
        .filter(DemoTeamHide.team_id == team_id, DemoTeamHide.user_id == user_id)
        .first()
        is not None
    )


def hide_demo_team(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    hidden = (
        db.query(DemoTeamHide)
        .filter(DemoTeamHide.team_id == team_id, DemoTeamHide.user_id == user_id)
        .first()
    )
    if hidden:
        return
    db.add(DemoTeamHide(team_id=team_id, user_id=user_id))
    db.commit()


def unhide_demo_team(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    hidden = (
        db.query(DemoTeamHide)
        .filter(DemoTeamHide.team_id == team_id, DemoTeamHide.user_id == user_id)
        .first()
    )
    if not hidden:
        return
    db.delete(hidden)
    db.commit()


def can_read_team(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    team = get_team(db, team_id)
    if not team:
        return False
    if team.is_demo:
        return not is_demo_team_hidden(db, team_id=team_id, user_id=user_id)
    return is_team_member(db, team_id=team_id, user_id=user_id)


def can_write_team(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    team = get_team(db, team_id)
    if not team or team.is_demo:
        return False
    return is_team_member(db, team_id=team_id, user_id=user_id)
