import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.change_batch import get_last_batch, restore_batch
from app.crud.team import is_team_member

router = APIRouter()


@router.post("/undo", status_code=status.HTTP_200_OK)
def undo_last_change(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    if not is_team_member(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    batch = get_last_batch(db, team_id=team_id, user_id=current_user.id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No change batch to undo")
    restore_batch(db, batch=batch)
    return {"message": "ok"}
