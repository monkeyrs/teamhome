from __future__ import annotations

import datetime as dt


APP_TIMEZONE = dt.timezone(dt.timedelta(hours=8))


def now_in_app_timezone() -> dt.datetime:
    return dt.datetime.now(APP_TIMEZONE)


def to_app_timezone(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def iso_in_app_timezone(value: dt.datetime | None) -> str | None:
    localized = to_app_timezone(value)
    return localized.isoformat() if localized else None
