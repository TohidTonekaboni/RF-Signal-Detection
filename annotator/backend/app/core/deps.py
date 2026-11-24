import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: AsyncSession = Depends(get_db)
) -> User:
    """Authenticated + active user. Allowed even while a password change is pending (used by /auth/*)."""
    if creds is None:
        raise AppError(401, "unauthorized")
    try:
        payload = decode_access_token(creds.credentials)
        user = await db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, ValueError):
        raise AppError(401, "unauthorized") from None
    if user is None or not user.active:
        raise AppError(401, "unauthorized")
    return user


async def active_user(user: User = Depends(current_user)) -> User:
    if user.must_change_password:
        raise AppError(403, "password_change_required")
    return user


def require_roles(*roles: str):
    async def dep(user: User = Depends(active_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden")
        return user

    return dep


@dataclass
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)) -> Pagination:
    return Pagination(page, page_size)


def utc(dt: datetime | None) -> datetime | None:
    """Treat naive datetimes in query strings as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
