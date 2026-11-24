from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import current_user
from app.core.errors import AppError
from app.core.security import (
    burn_password_check,
    check_password_policy,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.db.types import utcnow
from app.models import LoginAttempt, RefreshSession, User
from app.schemas import ChangePasswordIn, LoginIn, TokenOut, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "refresh_token"


def _set_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(COOKIE, raw, max_age=s.refresh_token_days * 86400, httponly=True, secure=s.cookie_secure,
                        samesite="strict", path="/api/auth")


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api/auth")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _new_session(db: AsyncSession, user: User, request: Request, response: Response) -> None:
    raw = new_refresh_token()
    db.add(RefreshSession(user_id=user.id, token_hash=hash_token(raw),
                          expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
                          user_agent=(request.headers.get("user-agent") or "")[:255] or None, ip=_ip(request)))
    _set_cookie(response, raw)


def _token_out(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


async def _check_lockout(db: AsyncSession, username: str, ip: str | None) -> None:
    s = get_settings()
    since = utcnow() - timedelta(minutes=s.lockout_window_minutes)
    by_user = await db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.username == username, LoginAttempt.success.is_(False), LoginAttempt.at > since))
    by_ip = 0
    if ip:
        by_ip = await db.scalar(select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.ip == ip, LoginAttempt.success.is_(False), LoginAttempt.at > since))
    if (by_user or 0) >= s.lockout_max_failures or (by_ip or 0) >= s.lockout_ip_max_failures:
        raise AppError(429, "too_many_attempts", "Too many failed logins; try again later",
                       headers={"Retry-After": str(s.lockout_window_minutes * 60)})


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    username = body.username.strip().lower()[:64]
    ip = _ip(request)
    await _check_lockout(db, username, ip)
    user = await db.scalar(select(User).where(User.username == username))
    ok = False
    if user is not None:
        ok = await verify_password(body.password, user.password_hash)
    else:
        await burn_password_check(body.password)
    if not ok or not user.active:
        db.add(LoginAttempt(username=username, ip=ip, success=False))
        await db.commit()
        raise AppError(401, "invalid_credentials")
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username == username, LoginAttempt.success.is_(False)))
    user.last_login_at = utcnow()
    await _new_session(db, user, request, response)
    audit(db, user, "auth.login")
    await db.commit()
    return _token_out(user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise AppError(401, "unauthorized")
    sess = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == hash_token(raw)))
    now = utcnow()
    if sess is None or sess.expires_at <= now:
        _clear_cookie(response)
        raise AppError(401, "unauthorized")
    user = await db.get(User, sess.user_id)
    if user is None or not user.active:
        raise AppError(401, "unauthorized")
    if sess.revoked_at is not None:
        if sess.rotated_at is None:
            # Revoked by logout / password change / admin action: never usable again, no grace.
            _clear_cookie(response)
            raise AppError(401, "unauthorized")
        # Rotated away. Two tabs refreshing concurrently present the same cookie, so tolerate a short grace window.
        if (now - sess.rotated_at).total_seconds() <= get_settings().refresh_grace_seconds:
            return _token_out(user)
        # A long-rotated token being replayed means it leaked: kill every session of this user.
        await db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id,
                                                      RefreshSession.revoked_at.is_(None)).values(revoked_at=now))
        audit(db, user, "auth.refresh_reuse_detected")
        await db.commit()
        _clear_cookie(response)
        raise AppError(401, "unauthorized")
    sess.revoked_at = sess.rotated_at = now  # rotate
    await _new_session(db, user, request, response)
    await db.commit()
    return _token_out(user)


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(COOKIE)
    if raw:
        await db.execute(update(RefreshSession).where(RefreshSession.token_hash == hash_token(raw),
                                                      RefreshSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
        await db.commit()
    resp = Response(status_code=204)
    _clear_cookie(resp)
    return resp


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


@router.post("/change-password", status_code=204, response_class=Response)
async def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(current_user),
                          db: AsyncSession = Depends(get_db)):
    if not await verify_password(body.current_password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Current password is wrong")
    check_password_policy(body.new_password, user.username)
    if body.new_password == body.current_password:
        raise AppError(422, "weak_password", "New password must differ from the current one")
    user.password_hash = await hash_password(body.new_password)
    user.must_change_password = False
    keep = None
    raw = request.cookies.get(COOKIE)
    if raw:
        keep = await db.scalar(select(RefreshSession.id).where(RefreshSession.token_hash == hash_token(raw)))
    stmt = update(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
    if keep is not None:
        stmt = stmt.where(RefreshSession.id != keep)
    await db.execute(stmt.values(revoked_at=utcnow()))
    audit(db, user, "auth.change_password")
    await db.commit()
    return Response(status_code=204)
