import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.finance import create_finance_record, list_finance_records
from app.crud.team import is_team_member
from app.schemas.finance import (
    FinanceAssistantIn,
    FinanceAssistantOut,
    FinanceCreate,
    FinanceOut,
    FinanceParseIn,
    FinanceParseOut,
)
from app.services.llm.parser import parse_finance_text
from app.services.llm.assistant import answer_finance_question

router = APIRouter()


@router.get("")
def list_finance_route(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[FinanceOut]:
    if not is_team_member(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    items = list_finance_records(db, team_id=team_id)
    return [FinanceOut.model_validate(r, from_attributes=True) for r in items]


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
        note=payload.note,
    )
    return FinanceOut.model_validate(record, from_attributes=True)


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
    result = answer_finance_question(db, team_id=payload.team_id, question=payload.question)
    return FinanceAssistantOut(answer=result.get("answer", ""), data=result.get("data"))
