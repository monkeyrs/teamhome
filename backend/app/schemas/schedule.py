import datetime as dt
import uuid

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    team_id: uuid.UUID
    title: str
    description: str | None = None
    start_time: dt.datetime
    end_time: dt.datetime | None = None


class ScheduleOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    title: str
    description: str | None = None
    start_time: dt.datetime
    end_time: dt.datetime | None = None
    created_by: uuid.UUID
    status: str


class ScheduleParseIn(BaseModel):
    text: str


class ScheduleParseOut(BaseModel):
    title: str | None = None
    start_time: str | None = None
    end_time: str | None = None
