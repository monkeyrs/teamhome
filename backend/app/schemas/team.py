import uuid

from pydantic import BaseModel


class TeamCreate(BaseModel):
    name: str


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
