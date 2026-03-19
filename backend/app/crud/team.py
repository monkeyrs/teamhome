import uuid

from sqlalchemy.orm import Session

from app.models.team import Team, TeamMember


def create_team(db: Session, *, name: str, owner_id: uuid.UUID) -> Team:
    team = Team(name=name, owner_id=owner_id)
    db.add(team)
    db.commit()
    db.refresh(team)

    membership = TeamMember(team_id=team.id, user_id=owner_id, role="admin")
    db.add(membership)
    db.commit()
    return team


def get_team(db: Session, team_id: uuid.UUID) -> Team | None:
    return db.query(Team).filter(Team.id == team_id).first()


def list_teams_for_user(db: Session, user_id: uuid.UUID) -> list[Team]:
    return (
        db.query(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == user_id)
        .order_by(Team.created_at.desc())
        .all()
    )


def is_team_member(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
        is not None
    )
