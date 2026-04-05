from __future__ import annotations

import logging
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.i18n import normalize_locale, translate
from app.crud.team import can_read_team
from app.schemas.assistant import AssistantExecuteIn, AssistantExecuteOut, AssistantUndoIn
from app.services.assistant_orchestrator import (
    execute_assistant,
    get_assistant_graph_state,
    get_orchestration_debug,
    message_requires_write_access,
    undo_last_assistant_batch,
)
from app.services.data_export_service import build_user_data_export

from app.services.llm.transcribe import TranscriptionError, transcribe_audio_file

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), current_user=Depends(get_current_user)) -> dict:
    settings = get_settings()
    filename = file.filename or "audio.wav"
    suffix = (os.path.splitext(filename)[1] or ".wav").lower()
    content_type = (file.content_type or "").lower()
    if suffix not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="AUDIO_TYPE_NOT_ALLOWED")
    if content_type and content_type not in settings.ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="AUDIO_TYPE_NOT_ALLOWED")

    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AUDIO_FILE_EMPTY")
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="AUDIO_FILE_TOO_LARGE")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        temp_path = temp_file.name

    try:
        text = transcribe_audio_file(temp_path)
        return {"text": text}
    except TranscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/execute")
def execute(
    payload: AssistantExecuteIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AssistantExecuteOut:
    if not can_read_team(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    if message_requires_write_access(db, team_id=payload.team_id, user_id=current_user.id, message=payload.message, locale=normalize_locale(getattr(current_user, "language", None))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_READ_ONLY")

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
    except Exception as exc:
        logger.exception("Assistant execute failed", extra={"team_id": str(payload.team_id), "user_id": str(current_user.id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=translate(locale, "assistant.internal_error"),
        ) from exc
    return AssistantExecuteOut(**result)


@router.post("/undo")
def undo(
    payload: AssistantUndoIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AssistantExecuteOut:
    if not can_read_team(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    if message_requires_write_access(
        db,
        team_id=payload.team_id,
        user_id=current_user.id,
        message="__assistant_undo_batch__",
        locale=normalize_locale(getattr(current_user, "language", None)),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TEAM_READ_ONLY")
    locale = normalize_locale(getattr(current_user, "language", None))
    try:
        result = undo_last_assistant_batch(
            db,
            team_id=payload.team_id,
            user_id=current_user.id,
            locale=locale,
        )
    except Exception as exc:
        logger.exception("Assistant undo failed", extra={"team_id": str(payload.team_id), "user_id": str(current_user.id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=translate(locale, "assistant.internal_error"),
        ) from exc
    return AssistantExecuteOut(**result)


@router.get("/graph-state")
def graph_state(
    team_id: uuid.UUID,
    session_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    if not can_read_team(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    return {"graph_state": get_assistant_graph_state(session_id=session_id)}


@router.get("/orchestration")
def orchestration(current_user=Depends(get_current_user)) -> dict:
    if not get_settings().debug_endpoints_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return get_orchestration_debug()


@router.get("/export-data")
def export_data(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    filename, payload = build_user_data_export(db=db, user_id=current_user.id)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
