from __future__ import annotations

import datetime as dt
import io
import uuid
from decimal import Decimal

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.crud.finance import list_finance_records
from app.crud.schedule import list_schedules
from app.crud.team import list_teams_for_user


_LOCAL_TZ = dt.timezone(dt.timedelta(hours=8))


def _format_datetime(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    localized = value.astimezone(_LOCAL_TZ) if value.tzinfo else value.replace(tzinfo=_LOCAL_TZ)
    return localized.strftime("%Y-%m-%d %H:%M:%S")


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.01")), "f")


def build_user_data_export(*, db: Session, user_id: uuid.UUID) -> tuple[str, bytes]:
    workbook = Workbook()
    schedule_sheet = workbook.active
    schedule_sheet.title = "Schedules"
    finance_sheet = workbook.create_sheet("Finance")

    schedule_sheet.append(
        [
            "Team ID",
            "Team Name",
            "Schedule ID",
            "Title",
            "Description",
            "Location",
            "All Day",
            "Start Time",
            "End Time",
            "Status",
            "Created By",
            "Created At",
        ]
    )
    finance_sheet.append(
        [
            "Team ID",
            "Team Name",
            "Record ID",
            "Type",
            "Nature",
            "Amount",
            "Occurred At",
            "Location",
            "Note",
            "Created By",
            "Created At",
        ]
    )

    teams = list_teams_for_user(db, user_id=user_id)
    for team in teams:
        schedules = list_schedules(db, team_id=team.id)
        for item in schedules:
            schedule_sheet.append(
                [
                    str(team.id),
                    team.name,
                    str(item.id),
                    item.title or "",
                    item.description or "",
                    item.location or "",
                    "Yes" if item.is_all_day else "No",
                    _format_datetime(item.start_time),
                    _format_datetime(item.end_time),
                    item.status or "",
                    str(item.created_by),
                    _format_datetime(item.created_at),
                ]
            )

        finance_records = list_finance_records(db, team_id=team.id)
        for item in finance_records:
            finance_sheet.append(
                [
                    str(team.id),
                    team.name,
                    str(item.id),
                    item.type or "",
                    item.category or "",
                    _format_decimal(item.amount),
                    _format_datetime(item.occurred_at),
                    item.location or "",
                    item.note or "",
                    str(item.user_id),
                    _format_datetime(item.created_at),
                ]
            )

    for sheet in (schedule_sheet, finance_sheet):
        for column_cells in sheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter
            for cell in column_cells:
                text = "" if cell.value is None else str(cell.value)
                if len(text) > max_length:
                    max_length = len(text)
            sheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 42)

    buffer = io.BytesIO()
    workbook.save(buffer)
    filename = f"teamhome-data-{dt.datetime.now(_LOCAL_TZ).strftime('%Y%m%d-%H%M%S')}.xlsx"
    return filename, buffer.getvalue()
