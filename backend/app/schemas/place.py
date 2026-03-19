import uuid

from pydantic import BaseModel


class PlaceOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    use_count: int
