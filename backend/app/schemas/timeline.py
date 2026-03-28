import uuid

from pydantic import BaseModel


class TimelineItemOut(BaseModel):
    kind: str
    source_id: uuid.UUID
    team_id: uuid.UUID
    occur_at: str
    created_at: str | None = None
    creator_name: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    is_all_day: bool | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str | None = None
    amount: str | None = None
    finance_type: str | None = None
    category: str | None = None
    note: str | None = None


class TimelineDayOut(BaseModel):
    day_key: str
    is_today: bool
    items: list[TimelineItemOut]


class TimelineResponseOut(BaseModel):
    days: list[TimelineDayOut]
