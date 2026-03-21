import uuid

from pydantic import BaseModel, Field


class AssistantExecuteIn(BaseModel):
    team_id: uuid.UUID
    message: str
    session_id: str | None = None


class AssistantUndoIn(BaseModel):
    team_id: uuid.UUID


class AssistantCard(BaseModel):
    type: str
    title: str
    body: str | None = None
    payload: dict | None = None


class AssistantExecuteOut(BaseModel):
    reply: str
    status: str
    intent: str | None = None
    session_id: str | None = None
    missing_slots: list[str] = Field(default_factory=list)
    pending_action: dict | None = None
    data: dict | None = None
    cards: list[AssistantCard] = Field(default_factory=list)
