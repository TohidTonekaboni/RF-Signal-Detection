"""Scheduled cleanup. Runs inside the procrastinate worker; also callable from tests with fake storage."""
import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.types import utcnow
from app.models import BoundingBox, ExperimentImage, Image, ImageStatus, LoginAttempt, RefreshSession
from app.storage.s3 import Storage

log = logging.getLogger("app.housekeeping")


async def _remove_image(db: AsyncSession, storage: Storage, img: Image) -> None:
    s = get_settings()
    await storage.delete(s.s3_bucket_images, img.storage_key)
    if img.thumb_key:
        await storage.delete(s.s3_bucket_thumbs, img.thumb_key)
    ei_ids = select(ExperimentImage.id).where(ExperimentImage.image_id == img.id)
    await db.execute(delete(BoundingBox).where(BoundingBox.experiment_image_id.in_(ei_ids)))
    await db.execute(delete(ExperimentImage).where(ExperimentImage.image_id == img.id))
    await db.delete(img)


async def run_housekeeping(db: AsyncSession, storage: Storage) -> dict[str, int]:
    s = get_settings()
    now = utcnow()
    out = {"sessions": 0, "attempts": 0, "pending_images": 0, "deleted_images": 0}

    r = await db.execute(delete(RefreshSession).where(RefreshSession.expires_at < now - timedelta(days=7)))
    out["sessions"] = r.rowcount or 0
    r = await db.execute(delete(LoginAttempt).where(LoginAttempt.at < now - timedelta(days=7)))
    out["attempts"] = r.rowcount or 0

    stale = (await db.scalars(select(Image).where(
        Image.status == ImageStatus.pending.value,
        Image.created_at < now - timedelta(hours=s.pending_upload_ttl_hours)))).unique().all()
    for img in stale:
        await _remove_image(db, storage, img)
    out["pending_images"] = len(stale)

    gone = (await db.scalars(select(Image).where(
        Image.deleted_at.is_not(None), Image.deleted_at < now - timedelta(days=s.deleted_retention_days)))).unique().all()
    for img in gone:
        await _remove_image(db, storage, img)
    out["deleted_images"] = len(gone)

    await db.commit()
    log.info("housekeeping done", extra={"user": str(out)})
    return out
