import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.team import Team, TeamMember


def create_team(db: Session, *, name: str, owner_id: uuid.UUID, join_password: str | None = None) -> Team:
    team = Team(name=name, owner_id=owner_id, join_password=join_password)
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
        .options(joinedload(Team.members))
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
        .options(joinedload(Team.members))
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


def count_team_members(db: Session, *, team_id: uuid.UUID) -> int:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id).count()


def is_team_member(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
        is not None
    )


def get_team_member(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMember | None:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()


def remove_team_member(db: Session, *, membership: TeamMember) -> None:
    db.delete(membership)
    db.commit()
