import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.place import list_places
from app.crud.team import is_team_member
from app.schemas.place import PlaceOut

router = APIRouter()


@router.get("")
def list_places_route(
    team_id: uuid.UUID,
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[PlaceOut]:
    if not is_team_member(db, team_id=team_id, user_id=current_user.id):
        return []
    items = list_places(db, team_id=team_id, query=q, limit=20)
    return [PlaceOut.model_validate(item, from_attributes=True) for item in items]
