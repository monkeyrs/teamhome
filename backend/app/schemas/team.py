import re
import uuid

from pydantic import BaseModel, field_validator


class TeamCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Team name required")
        if len(normalized) > 20:
            raise ValueError("Team name must be within 20 characters")
        if not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", normalized):
            raise ValueError("Team name supports Chinese, letters, and numbers only")
        return normalized


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
