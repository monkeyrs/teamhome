from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.i18n import normalize_locale, translate
from app.crud.team import is_team_member
from app.schemas.assistant import AssistantExecuteIn, AssistantExecuteOut, AssistantUndoIn
from app.services.assistant_orchestrator import execute_assistant, undo_last_assistant_batch
from sqlalchemy.orm import Session

from app.services.llm.transcribe import transcribe_audio_file

router = APIRouter()


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name

    try:
        text = transcribe_audio_file(temp_path)
        return {"text": text}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/execute")
def execute(
    payload: AssistantExecuteIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AssistantExecuteOut:
    if not is_team_member(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")

    locale = normalize_locale(getattr(current_user, "language", None))
    try:
        result = execute_assistant(
            db,
            team_id=payload.team_id,
            user_id=current_user.id,
            message=payload.message,
            session_id=payload.session_id,
            locale=locale,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception:
        result = {
            "reply": translate(locale, "assistant.internal_error"),
            "status": "unsupported",
            "intent": "unsupported",
            "session_id": None,
            "missing_slots": [],
            "pending_action": None,
            "data": {"can_undo": False},
            "cards": [],
        }

    return AssistantExecuteOut(**result)


@router.post("/undo")
def undo(
    payload: AssistantUndoIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AssistantExecuteOut:
    if not is_team_member(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    locale = normalize_locale(getattr(current_user, "language", None))
    try:
        result = undo_last_assistant_batch(
            db,
            team_id=payload.team_id,
            user_id=current_user.id,
            locale=locale,
        )
    except Exception:
        result = {
            "reply": translate(locale, "assistant.internal_error"),
            "status": "unsupported",
            "intent": "unsupported",
            "session_id": None,
            "missing_slots": [],
            "pending_action": None,
            "data": {"can_undo": False},
            "cards": [],
        }
    return AssistantExecuteOut(**result)
