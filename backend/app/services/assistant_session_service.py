from __future__ import annotations

import copy
import datetime as dt
import uuid

from app.core.database import SessionLocal
from app.crud.assistant_state import (
    create_or_replace_assistant_session,
    delete_assistant_session,
    get_assistant_session,
    pop_assistant_undo_batch,
    save_assistant_undo_batch,
)

_SERIALIZED_TYPE_KEY = "__teamhome_type__"
_SERIALIZED_VALUE_KEY = "value"
_DATETIME_TYPE = "datetime"


def _serialize_session_value(value):
    if isinstance(value, dt.datetime):
        return {
            _SERIALIZED_TYPE_KEY: _DATETIME_TYPE,
            _SERIALIZED_VALUE_KEY: value.isoformat(),
        }
    if isinstance(value, list):
        return [_serialize_session_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_session_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _serialize_session_value(item)
            for key, item in value.items()
        }
    return value


def _deserialize_session_value(value):
    if isinstance(value, list):
        return [_deserialize_session_value(item) for item in value]
    if isinstance(value, dict):
        serialized_type = value.get(_SERIALIZED_TYPE_KEY)
        if serialized_type == _DATETIME_TYPE:
            raw_value = value.get(_SERIALIZED_VALUE_KEY)
            if isinstance(raw_value, str):
                try:
                    return dt.datetime.fromisoformat(raw_value)
                except ValueError:
                    return raw_value
        return {
            key: _deserialize_session_value(item)
            for key, item in value.items()
        }
    return value


def create_session(state: dict) -> str:
    session_id = str(uuid.uuid4())
    save_session(session_id, state)
    return session_id


def get_session(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    with SessionLocal() as db:
        session = get_assistant_session(db, session_id=session_id)
        if session is None:
            return None
        return _deserialize_session_value(copy.deepcopy(session.state or {}))


def save_session(session_id: str, state: dict) -> None:
    with SessionLocal() as db:
        create_or_replace_assistant_session(
            db,
            session_id=session_id,
            state=_serialize_session_value(copy.deepcopy(state)),
        )


def clear_session(session_id: str | None) -> None:
    if not session_id:
        return
    with SessionLocal() as db:
        delete_assistant_session(db, session_id=session_id)


def save_undo_batch(team_id: uuid.UUID, user_id: uuid.UUID, actions: list[dict]) -> None:
    with SessionLocal() as db:
        save_assistant_undo_batch(
            db,
            team_id=team_id,
            user_id=user_id,
            actions=copy.deepcopy(actions),
        )


def pop_undo_batch(team_id: uuid.UUID, user_id: uuid.UUID) -> list[dict] | None:
    with SessionLocal() as db:
        actions = pop_assistant_undo_batch(db, team_id=team_id, user_id=user_id)
        if actions is None:
            return None
        return copy.deepcopy(actions)
