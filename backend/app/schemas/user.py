import uuid

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: uuid.UUID
    wechat_openid: str
    nickname: str | None = None
    avatar: str | None = None
    language: str = "zh-CN"


class AuthLoginIn(BaseModel):
    code: str = Field(..., description="WeChat login code")
    nickname: str | None = None
    avatar: str | None = None
    language: str | None = None


class AuthLoginOut(BaseModel):
    token: str
    user: UserOut


class UserProfileUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=20)
    language: str | None = None
