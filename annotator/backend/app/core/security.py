import asyncio
import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AppError

_hasher = PasswordHash.recommended()  # argon2id
_ALGO = "HS256"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_dummy_hash: str | None = None


def hash_password_sync(password: str) -> str:
    return _hasher.hash(password)


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    return await asyncio.to_thread(_hasher.verify, password, hashed)


async def burn_password_check(password: str) -> None:
    """Equalise timing for unknown usernames."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = await hash_password("not-a-real-password")
    await verify_password(password, _dummy_hash)


def check_password_policy(password: str, username: str | None = None) -> None:
    if len(password) < 8 or len(password) > 128:
        raise AppError(422, "weak_password", "Password must be 8–128 characters")
    if username and password.lower() == username.lower():
        raise AppError(422, "weak_password", "Password must differ from the username")


def create_access_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "typ": "access", "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=_ALGO)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGO], options={"require": ["exp", "sub"]})
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def temporary_password() -> str:
    return secrets.token_urlsafe(9)  # 12 chars
