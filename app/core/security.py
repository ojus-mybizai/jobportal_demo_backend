from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from argon2 import PasswordHasher
from jose import JWTError, jwt

from app.core.config import settings


password_hasher = PasswordHasher()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        password_hasher.verify(hashed_password, plain_password)
        return True
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return password_hasher.hash(password)


def _create_token(subject: str | Any, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode = {"sub": str(subject), "exp": expire, "type": token_type}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_access_token(subject: str | Any, expires_minutes: Optional[int] = None) -> str:
    if expires_minutes is None:
        expires_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    return _create_token(subject, timedelta(minutes=expires_minutes), token_type="access")


def create_refresh_token(subject: str | Any, expires_minutes: Optional[int] = None) -> str:
    if expires_minutes is None:
        expires_minutes = settings.REFRESH_TOKEN_EXPIRE_MINUTES
    return _create_token(subject, timedelta(minutes=expires_minutes), token_type="refresh")


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Could not validate credentials") from exc
    return payload
