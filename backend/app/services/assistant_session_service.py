from __future__ import annotations

import copy
import uuid


_SESSIONS: dict[str, dict] = {}


def create_session(state: dict) -> str:
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = copy.deepcopy(state)
    return session_id


def get_session(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    state = _SESSIONS.get(session_id)
    return copy.deepcopy(state) if state else None


def save_session(session_id: str, state: dict) -> None:
    _SESSIONS[session_id] = copy.deepcopy(state)


def clear_session(session_id: str | None) -> None:
    if session_id:
        _SESSIONS.pop(session_id, None)
