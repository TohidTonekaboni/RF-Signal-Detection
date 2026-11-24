from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Pagination, require_roles, utc
from app.db.session import get_db
from app.models import AuditLog, Role, User
from app.schemas import AuditOut, Page

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditOut])
async def list_audit(date_from: datetime | None = Query(None, alias="from"), date_to: datetime | None = Query(None, alias="to"),
                     actor: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200),
                     _: User = Depends(require_roles(Role.admin)), db: AsyncSession = Depends(get_db)):
    # The UI's audit tab has no pager yet, hence the larger default page.
    pg = Pagination(page, page_size)
    conds = []
    if date_from:
        conds.append(AuditLog.at >= utc(date_from))
    if date_to:
        conds.append(AuditLog.at <= utc(date_to))
    if actor:
        conds.append(AuditLog.actor == actor.lower())
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*conds))
    rows = await db.scalars(select(AuditLog).where(*conds).order_by(AuditLog.at.desc(), AuditLog.id.desc())
                            .offset(pg.offset).limit(pg.page_size))
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total or 0, page=pg.page, page_size=pg.page_size)
