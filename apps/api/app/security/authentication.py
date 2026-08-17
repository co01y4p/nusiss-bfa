from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.models import UserModel

password_hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    role: str


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user: UserModel, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "iss": settings.app_name,
        "aud": "bfa-api",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="bfa-api",
            issuer=settings.app_name,
        )
        user_id = payload.get("sub")
        if not isinstance(user_id, str):
            raise unauthorized
    except jwt.PyJWTError as exc:
        raise unauthorized from exc
    user = db.scalar(
        select(UserModel).where(UserModel.id == user_id, UserModel.is_active.is_(True))
    )
    if user is None:
        raise unauthorized
    return CurrentUser(id=user.id, email=user.email, role=user.role)


def require_manager(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.role != "MANAGER":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return user
