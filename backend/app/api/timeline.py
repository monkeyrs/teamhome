import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.finance import list_finance_records
from app.crud.schedule import list_schedules
from app.crud.team import can_read_team
from app.schemas.timeline import TimelineDayOut, TimelineItemOut, TimelineResponseOut

router = APIRouter()

TIMELINE_KIND_SCHEDULE = "schedule"
TIMELINE_KIND_INCOME = "income"
TIMELINE_KIND_EXPENSE = "expense"
ALLOWED_KINDS = {
    TIMELINE_KIND_SCHEDULE,
    TIMELINE_KIND_INCOME,
    TIMELINE_KIND_EXPENSE,
}
MAX_WINDOW_DAYS = 366


def iso_or_none(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def day_key_from_iso(value: str) -> str:
    return value[:10]


def parse_kind_list(raw: str | None) -> set[str]:
    if not raw:
        return set(ALLOWED_KINDS)
    kinds = {item.strip() for item in raw.split(",") if item and item.strip()}
    if not kinds or not kinds.issubset(ALLOWED_KINDS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timeline kinds")
    return kinds


def validate_window(window_start: dt.datetime | None, window_end: dt.datetime | None) -> None:
    if window_start and window_end and window_start > window_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="window_start must be <= window_end")
    if window_start and window_end and (window_end - window_start) > dt.timedelta(days=MAX_WINDOW_DAYS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Timeline window is too large")


def build_schedule_item(item) -> TimelineItemOut:
    occur_at = iso_or_none(item.start_time) or iso_or_none(item.created_at) or ""
    return TimelineItemOut.model_validate(
        {
            "kind": TIMELINE_KIND_SCHEDULE,
            "source_id": item.id,
            "team_id": item.team_id,
            "occur_at": occur_at,
            "created_at": iso_or_none(item.created_at),
            "creator_name": getattr(getattr(item, "creator", None), "nickname", None),
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "is_all_day": item.is_all_day,
            "start_time": iso_or_none(item.start_time),
            "end_time": iso_or_none(item.end_time),
            "status": item.status,
        }
    )


def build_finance_item(item) -> TimelineItemOut:
    occur_at = iso_or_none(item.occurred_at) or iso_or_none(item.created_at) or ""
    finance_kind = TIMELINE_KIND_INCOME if item.type == TIMELINE_KIND_INCOME else TIMELINE_KIND_EXPENSE
    return TimelineItemOut.model_validate(
        {
            "kind": finance_kind,
            "source_id": item.id,
            "team_id": item.team_id,
            "occur_at": occur_at,
            "created_at": iso_or_none(item.created_at),
            "creator_name": getattr(getattr(item, "user", None), "nickname", None),
            "title": item.category or finance_kind,
            "location": item.location,
            "amount": str(item.amount),
            "finance_type": item.type,
            "category": item.category,
            "note": item.note,
        }
    )


def group_items(items: list[TimelineItemOut]) -> list[TimelineDayOut]:
    today_key = dt.datetime.now(dt.timezone.utc).astimezone().date().isoformat()
    grouped: dict[str, list[TimelineItemOut]] = {}
    for item in items:
        grouped.setdefault(day_key_from_iso(item.occur_at), []).append(item)

    days: list[TimelineDayOut] = []
    for day_key in sorted(grouped.keys(), reverse=True):
        day_items = sorted(
            grouped[day_key],
            key=lambda item: (
                item.occur_at,
                0 if item.kind == TIMELINE_KIND_SCHEDULE else 1,
                item.created_at or "",
            ),
            reverse=True,
        )
        days.append(
            TimelineDayOut.model_validate(
                {
                    "day_key": day_key,
                    "is_today": day_key == today_key,
                    "items": day_items,
                }
            )
        )
    return days


@router.get("")
def list_timeline_route(
    team_id: uuid.UUID,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
    kinds: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TimelineResponseOut:
    if not can_read_team(db, team_id=team_id, user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")

    validate_window(window_start, window_end)
    selected_kinds = parse_kind_list(kinds)

    items: list[TimelineItemOut] = []
    if TIMELINE_KIND_SCHEDULE in selected_kinds:
        schedules = list_schedules(db, team_id=team_id, window_start=window_start, window_end=window_end)
        items.extend(build_schedule_item(item) for item in schedules)

    finance_kinds = {TIMELINE_KIND_INCOME, TIMELINE_KIND_EXPENSE}.intersection(selected_kinds)
    if finance_kinds:
        finance_records = list_finance_records(db, team_id=team_id, window_start=window_start, window_end=window_end)
        for record in finance_records:
            finance_kind = TIMELINE_KIND_INCOME if record.type == TIMELINE_KIND_INCOME else TIMELINE_KIND_EXPENSE
            if finance_kind in finance_kinds:
                items.append(build_finance_item(record))

    items.sort(
        key=lambda item: (
            item.occur_at,
            0 if item.kind == TIMELINE_KIND_SCHEDULE else 1,
            item.created_at or "",
        ),
        reverse=True,
    )
    return TimelineResponseOut(days=group_items(items))
