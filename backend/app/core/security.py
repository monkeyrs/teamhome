import datetime as dt

from jose import JWTError, jwt

from app.core.config import get_settings


def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    exp = now + dt.timedelta(minutes=settings.JWT_EXPIRES_MINUTES)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": exp}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError as e:
        raise ValueError("Invalid token") from e
