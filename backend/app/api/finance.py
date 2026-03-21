import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.i18n import normalize_locale
from app.crud.change_batch import create_change_batch, prune_old_batches
from app.crud.finance import (
    create_finance_record,
    get_finance_record,
    list_finance_records,
    list_popular_categories,
    soft_delete_finance_record,
    update_finance_record,
)
from app.crud.place import touch_place
from app.crud.team import is_team_member
from app.schemas.finance import (
    FinanceAssistantIn,
    FinanceAssistantOut,
    FinanceCreate,
    FinanceOut,
    FinanceParseIn,
    FinanceParseOut,
    FinanceUpdate,
)
from app.services.llm.parser import parse_finance_text
from app.services.llm.assistant import answer_finance_question

router = APIRouter()


def to_finance_out(item) -> FinanceOut:
    created_at = item.created_at.isoformat() if getattr(item, "created_at", None) else None
    occurred_at = item.occurred_at.isoformat() if getattr(item, "occurred_at", None) else created_at
    return FinanceOut.model_validate(
        {
            "id": item.id,
            "team_id": item.team_id,
            "user_id": item.user_id,
            "creator_nickname": getattr(getattr(item, "user", None), "nickname", None),
            "amount": item.amount,
            "type": item.type,
            "category": item.category,
            "occurred_at": occurred_at,
            "location": item.location,
            "location_latitude": item.location_latitude,
            "location_longitude": item.location_longitude,
            "note": item.note,
            "created_at": created_at,
        }
    )


def parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


@router.get("")
def list_finance_route(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[FinanceOut]:
    if not is_team_member(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    items = list_finance_records(db, team_id=team_id)
    return [to_finance_out(item) for item in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_finance_route(
    payload: FinanceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> FinanceOut:
    if not is_team_member(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    record = create_finance_record(
        db,
        team_id=payload.team_id,
        user_id=current_user.id,
        amount=payload.amount,
        record_type=payload.type,
        category=payload.category,
        occurred_at=parse_optional_datetime(payload.occurred_at),
        location=payload.location,
        location_latitude=payload.location_latitude,
        location_longitude=payload.location_longitude,
        note=payload.note,
    )
    touch_place(db, team_id=payload.team_id, name=payload.location or "")
    return to_finance_out(record)


@router.get("/categories")
def list_finance_categories_route(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[str]:
    if not is_team_member(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    return list_popular_categories(db, team_id=team_id, limit=5)


@router.post("/parse")
def parse_finance(payload: FinanceParseIn) -> FinanceParseOut:
    data = parse_finance_text(payload.text)
    return FinanceParseOut(**data)


@router.post("/assistant")
def finance_assistant(
    payload: FinanceAssistantIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> FinanceAssistantOut:
    if not is_team_member(db, team_id=payload.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    result = answer_finance_question(
        db,
        team_id=payload.team_id,
        question=payload.question,
        locale=normalize_locale(getattr(current_user, "language", None)),
    )
    return FinanceAssistantOut(answer=result.get("answer", ""), data=result.get("data"))


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_finance_route(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> None:
    record = get_finance_record(db, record_id=record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finance record not found")
    if not is_team_member(db, team_id=record.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    batch = create_change_batch(db, team_id=record.team_id, user_id=current_user.id, action="delete", entity_type="finance")
    soft_delete_finance_record(db, record=record, batch_id=batch.id)
    prune_old_batches(db, team_id=record.team_id, user_id=current_user.id, keep=3)


@router.put("/{record_id}")
def update_finance_route(
    record_id: uuid.UUID,
    payload: FinanceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> FinanceOut:
    record = get_finance_record(db, record_id=record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finance record not found")
    if not is_team_member(db, team_id=record.team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    record = update_finance_record(
        db,
        record=record,
        amount=payload.amount,
        record_type=payload.type,
        category=payload.category,
        occurred_at=parse_optional_datetime(payload.occurred_at),
        location=payload.location,
        location_latitude=payload.location_latitude,
        location_longitude=payload.location_longitude,
        note=payload.note,
    )
    touch_place(db, team_id=record.team_id, name=payload.location or "")
    return to_finance_out(record)
