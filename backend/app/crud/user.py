import uuid

from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_openid(db: Session, openid: str) -> User | None:
    return db.query(User).filter(User.wechat_openid == openid).first()


def get_or_create_user_by_openid(
    db: Session, openid: str, nickname: str | None = None, avatar: str | None = None
) -> User:
    user = get_user_by_openid(db, openid)
    if user:
        if nickname is not None:
            user.nickname = nickname
        if avatar is not None:
            user.avatar = avatar
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    user = User(wechat_openid=openid, nickname=nickname, avatar=avatar)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_profile(db: Session, *, user: User, nickname: str | None = None, avatar: str | None = None) -> User:
    if nickname is not None:
        user.nickname = nickname.strip()
    if avatar is not None:
        user.avatar = avatar
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
