from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.crud.user import get_or_create_user_by_openid
from app.schemas.user import AuthLoginIn, AuthLoginOut, UserOut
from app.services.auth_service import exchange_wechat_code_for_openid

router = APIRouter()


@router.post("/login")
async def login(payload: AuthLoginIn, db: Session = Depends(get_db)) -> AuthLoginOut:
    openid = await exchange_wechat_code_for_openid(payload.code)
    user = get_or_create_user_by_openid(db, openid, nickname=payload.nickname, avatar=payload.avatar)
    token = create_access_token(str(user.id))
    return AuthLoginOut(token=token, user=UserOut.model_validate(user, from_attributes=True))
