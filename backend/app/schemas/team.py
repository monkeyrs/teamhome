import re
import uuid

from pydantic import BaseModel, field_validator

TEAM_NAME_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
TEAM_PASSWORD_PATTERN = re.compile(r"\d{4}")


def normalize_team_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Team name required")
    if len(normalized) > 20:
        raise ValueError("Team name must be within 20 characters")
    if not TEAM_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("Team name supports Chinese, letters, and numbers only")
    return normalized


def normalize_team_password(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if not TEAM_PASSWORD_PATTERN.fullmatch(normalized):
        raise ValueError("Team password must be exactly 4 digits")
    return normalized


class TeamCreate(BaseModel):
    name: str
    password: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_team_name(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        return normalize_team_password(value)


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    is_demo: bool = False
    is_readonly: bool = False
    can_write: bool = True
    join_password: str | None = None
    member_count: int = 0


class TeamDiscoverOut(BaseModel):
    name: str
    exists: bool
    already_joined: bool
    requires_password: bool
    member_count: int
    team_full: bool
    is_demo: bool = False
