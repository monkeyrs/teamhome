import uuid

from sqlalchemy.orm import Session

from app.models.assistant_state import AssistantSession, AssistantUndoBatch


def create_or_replace_assistant_session(db: Session, *, session_id: str, state: dict) -> AssistantSession:
    session = db.get(AssistantSession, session_id)
    if session is None:
        session = AssistantSession(id=session_id, state=state)
    else:
        session.state = state
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_assistant_session(db: Session, *, session_id: str) -> AssistantSession | None:
    return db.get(AssistantSession, session_id)


def delete_assistant_session(db: Session, *, session_id: str) -> None:
    session = db.get(AssistantSession, session_id)
    if session is None:
        return
    db.delete(session)
    db.commit()


def save_assistant_undo_batch(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID, actions: list[dict]) -> None:
    existing = (
        db.query(AssistantUndoBatch)
        .filter(AssistantUndoBatch.team_id == team_id, AssistantUndoBatch.user_id == user_id)
        .first()
    )
    if not actions:
        if existing is not None:
            db.delete(existing)
            db.commit()
        return
    if existing is None:
        existing = AssistantUndoBatch(team_id=team_id, user_id=user_id, actions=actions)
    else:
        existing.actions = actions
    db.add(existing)
    db.commit()


def pop_assistant_undo_batch(db: Session, *, team_id: uuid.UUID, user_id: uuid.UUID) -> list[dict] | None:
    existing = (
        db.query(AssistantUndoBatch)
        .filter(AssistantUndoBatch.team_id == team_id, AssistantUndoBatch.user_id == user_id)
        .first()
    )
    if existing is None:
        return None
    actions = list(existing.actions or [])
    db.delete(existing)
    db.commit()
    return actions
