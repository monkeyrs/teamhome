import datetime as dt
import uuid

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    team_id: uuid.UUID
    title: str
    description: str | None = None
    location: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    is_all_day: bool = False
    start_time: dt.datetime
    end_time: dt.datetime | None = None


class ScheduleOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    title: str
    description: str | None = None
    location: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    is_all_day: bool
    start_time: dt.datetime
    end_time: dt.datetime | None = None
    created_by: uuid.UUID
    creator_nickname: str | None = None
    status: str
    created_at: dt.datetime | None = None


class ScheduleParseIn(BaseModel):
    text: str


class ScheduleParseOut(BaseModel):
    title: str | None = None
    start_time: str | None = None
    end_time: str | None = None
