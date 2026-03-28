from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.crud.user import get_or_create_user_by_openid, update_user_profile
from app.schemas.user import AuthLoginIn, AuthLoginOut, UserOut, UserProfileUpdateIn
from app.services.auth_service import exchange_wechat_code_for_openid
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/login")
async def login(payload: AuthLoginIn, db: Session = Depends(get_db)) -> AuthLoginOut:
    try:
        openid = await exchange_wechat_code_for_openid(payload.code)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WECHAT_LOGIN_UNAVAILABLE",
        ) from exc
    user = get_or_create_user_by_openid(
        db,
        openid,
        nickname=payload.nickname,
        language=payload.language,
    )
    token = create_access_token(str(user.id))
    return AuthLoginOut(token=token, user=UserOut.model_validate(user, from_attributes=True))


@router.get("/me")
def get_me(current_user=Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user, from_attributes=True)


@router.put("/me")
def update_me(
    payload: UserProfileUpdateIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> UserOut:
    if payload.nickname is not None:
        normalized_nickname = payload.nickname.strip()
        current_nickname = (current_user.nickname or "").strip()
        if current_nickname and normalized_nickname != current_nickname:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="NICKNAME_LOCKED",
            )
    user = update_user_profile(
        db,
        user=current_user,
        nickname=payload.nickname,
        language=payload.language,
    )
    return UserOut.model_validate(user, from_attributes=True)
