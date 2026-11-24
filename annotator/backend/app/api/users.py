import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.core.errors import AppError
from app.core.security import check_password_policy, hash_password, temporary_password
from app.db.session import get_db
from app.db.types import utcnow
from app.models import RefreshSession, Role, User
from app.schemas import TempPasswordOut, UserCreate, UserOut, UserPatch
from app.services.audit import audit

router = APIRouter(prefix="/users", tags=["users"])
admin_only = require_roles(Role.admin)


async def _get(db: AsyncSession, user_id: uuid.UUID) -> User:
    u = await db.get(User, user_id)
    if u is None:
        raise AppError(404, "not_found")
    return u


async def _revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(update(RefreshSession).where(RefreshSession.user_id == user_id,
                                                  RefreshSession.revoked_at.is_(None)).values(revoked_at=utcnow()))


async def _other_active_admins(db: AsyncSession, exclude: uuid.UUID) -> int:
    rows = await db.scalars(select(User.id).where(User.role == Role.admin, User.active.is_(True), User.id != exclude))
    return len(rows.all())


@router.get("", response_model=list[UserOut])
async def list_users(_: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(User).order_by(User.username))).all()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    username = body.username.lower()
    check_password_policy(body.password, username)
    user = User(username=username, role=body.role.value, password_hash=await hash_password(body.password),
                active=True, must_change_password=True)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "username_taken") from None
    audit(db, admin, "users.create", "user", user.id, {"username": username, "role": body.role.value})
    await db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(user_id: uuid.UUID, body: UserPatch, admin: User = Depends(admin_only),
                     db: AsyncSession = Depends(get_db)):
    user = await _get(db, user_id)
    losing_admin = (body.active is False and user.active and user.role == Role.admin) or (
        body.role is not None and body.role != Role.admin and user.role == Role.admin)
    if losing_admin and await _other_active_admins(db, user.id) == 0:
        raise AppError(409, "last_admin", "At least one active admin is required")
    if body.active is not None and body.active != user.active:
        user.active = body.active
        if not body.active:
            await _revoke_sessions(db, user.id)
        audit(db, admin, "users.activate" if body.active else "users.deactivate", "user", user.id)
    if body.role is not None and body.role.value != user.role:
        audit(db, admin, "users.set_role", "user", user.id, {"from": user.role, "to": body.role.value})
        user.role = body.role.value
    await db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=TempPasswordOut)
async def reset_password(user_id: uuid.UUID, response: Response, admin: User = Depends(admin_only),
                         db: AsyncSession = Depends(get_db)):
    """Offline deployment (no email): the admin hands the one-time password to the user, who must change it at login."""
    user = await _get(db, user_id)
    temp = temporary_password()
    user.password_hash = await hash_password(temp)
    user.must_change_password = True
    await _revoke_sessions(db, user.id)
    audit(db, admin, "users.reset_password", "user", user.id)
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return TempPasswordOut(temporary_password=temp)
