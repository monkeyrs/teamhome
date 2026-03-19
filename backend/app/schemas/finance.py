import decimal
import uuid

from pydantic import BaseModel


class FinanceCreate(BaseModel):
    team_id: uuid.UUID
    amount: decimal.Decimal
    type: str
    category: str
    location: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    note: str | None = None


class FinanceOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    user_id: uuid.UUID
    creator_nickname: str | None = None
    amount: decimal.Decimal
    type: str
    category: str
    location: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    note: str | None = None
    created_at: str | None = None


class FinanceParseIn(BaseModel):
    text: str


class FinanceParseOut(BaseModel):
    amount: float | None = None
    type: str | None = None
    category: str | None = None


class FinanceAssistantIn(BaseModel):
    team_id: uuid.UUID
    question: str


class FinanceAssistantOut(BaseModel):
    answer: str
    data: dict | None = None
