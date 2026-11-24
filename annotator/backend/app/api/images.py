import asyncio
import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import Pagination, active_user, pagination, require_roles, utc
from app.core.errors import AppError
from app.db.session import get_db
from app.db.types import utcnow
from app.models import Image, ImageStatus, Role, User
from app.schemas import ImageOut, ImagePatch, Page, PresignIn, PresignOut
from app.services.audit import audit
from app.services.imaging import EXT, InvalidImage, process_image
from app.services.serialize import image_out
from app.storage.s3 import Storage, get_storage

router = APIRouter(prefix="/images", tags=["images"])
uploaders = require_roles(Role.admin, Role.annotator)


def _live():
    return (Image.status == ImageStatus.ready.value, Image.deleted_at.is_(None))


async def _get_live(db: AsyncSession, image_id: uuid.UUID) -> Image:
    img = await db.scalar(select(Image).where(Image.id == image_id, *_live()))
    if img is None:
        raise AppError(404, "not_found")
    return img


@router.get("", response_model=Page[ImageOut])
async def list_images(
    q: str | None = Query(None, max_length=100),
    date_from: datetime | None = Query(None, alias="from", description="UTC instant, inclusive"),
    date_to: datetime | None = Query(None, alias="to", description="UTC instant, inclusive"),
    page: Pagination = Depends(pagination),
    _: User = Depends(active_user), db: AsyncSession = Depends(get_db), storage: Storage = Depends(get_storage),
):
    conds = list(_live())
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conds.append(Image.filename.ilike(f"%{esc}%", escape="\\"))
    if date_from:
        conds.append(Image.created_at >= utc(date_from))
    if date_to:
        conds.append(Image.created_at <= utc(date_to))
    total = await db.scalar(select(func.count()).select_from(Image).where(*conds))
    rows = (await db.scalars(select(Image).where(*conds).order_by(Image.created_at.desc(), Image.id)
                             .offset(page.offset).limit(page.page_size))).unique().all()
    return Page(items=[image_out(i, storage) for i in rows], total=total or 0, page=page.page, page_size=page.page_size)


@router.post("/presign", response_model=PresignOut, status_code=201)
async def presign(body: PresignIn, user: User = Depends(uploaders), db: AsyncSession = Depends(get_db),
                  storage: Storage = Depends(get_storage)):
    s = get_settings()
    if body.content_type not in EXT:
        raise AppError(415, "unsupported_media_type", "Only PNG and JPEG images are accepted")
    if body.size > s.max_upload_bytes:
        raise AppError(413, "file_too_large", f"Maximum upload size is {s.max_upload_mb} MB")
    now = utcnow()
    stem = f"{now:%Y}/{now:%m}/{uuid.uuid4()}"  # never derived from the user-supplied filename
    key = f"{stem}.{EXT[body.content_type]}"
    img = Image(filename=body.filename.strip()[:255], storage_key=key, content_type=body.content_type,
                size=body.size, status=ImageStatus.pending.value, uploaded_by=user.id, meta={})
    db.add(img)
    await db.commit()
    url = storage.presign_put(s.s3_bucket_images, key, body.content_type, s.presign_put_seconds)
    return PresignOut(image_id=img.id, upload_url=url)


async def _discard(db: AsyncSession, storage: Storage, img: Image) -> None:
    s = get_settings()
    await storage.delete(s.s3_bucket_images, img.storage_key)
    await db.delete(img)
    await db.commit()


@router.post("/{image_id}/complete", response_model=ImageOut)
async def complete(image_id: uuid.UUID, user: User = Depends(uploaders), db: AsyncSession = Depends(get_db),
                   storage: Storage = Depends(get_storage)):
    """Verify what the browser uploaded straight to MinIO, then publish the image."""
    s = get_settings()
    img = await db.scalar(select(Image).where(Image.id == image_id, Image.deleted_at.is_(None)))
    if img is None or (img.uploaded_by != user.id and user.role != Role.admin):
        raise AppError(404, "not_found")
    if img.status == ImageStatus.ready.value:
        return image_out(img, storage)  # idempotent retry

    size = await storage.size(s.s3_bucket_images, img.storage_key)
    if size is None:
        raise AppError(400, "upload_missing", "No uploaded object found for this image")
    if size > s.max_upload_bytes:
        await _discard(db, storage, img)
        raise AppError(413, "file_too_large")
    data = await storage.get(s.s3_bucket_images, img.storage_key)
    digest = hashlib.sha256(data).hexdigest()

    dup = await db.scalar(select(Image).where(Image.sha256 == digest, Image.id != img.id, *_live()))
    if dup is not None:
        await _discard(db, storage, img)
        raise AppError(409, "duplicate_image", "This image was already uploaded", {"existing_id": str(dup.id)})
    try:
        processed = await asyncio.to_thread(process_image, data)
    except InvalidImage as e:
        await _discard(db, storage, img)
        raise AppError(422, "invalid_image", str(e)) from None

    thumb_key = img.storage_key.rsplit(".", 1)[0] + ".jpg"
    await storage.put(s.s3_bucket_thumbs, thumb_key, processed.thumb, "image/jpeg")
    img.thumb_key = thumb_key
    img.sha256 = digest
    img.size = len(data)
    img.width, img.height = processed.width, processed.height
    img.content_type = processed.content_type
    img.meta = processed.meta
    img.status = ImageStatus.ready.value
    audit(db, user, "images.upload", "image", img.id, {"filename": img.filename})
    await db.commit()
    return image_out(img, storage)


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(image_id: uuid.UUID, _: User = Depends(active_user), db: AsyncSession = Depends(get_db),
                    storage: Storage = Depends(get_storage)):
    return image_out(await _get_live(db, image_id), storage)


@router.patch("/{image_id}", response_model=ImageOut)
async def patch_image(image_id: uuid.UUID, body: ImagePatch, user: User = Depends(uploaders),
                      db: AsyncSession = Depends(get_db), storage: Storage = Depends(get_storage)):
    img = await _get_live(db, image_id)
    img.meta = {**(img.meta or {}), **body.meta.model_dump(exclude_none=True)}
    audit(db, user, "images.update_meta", "image", img.id)
    await db.commit()
    return image_out(img, storage)


@router.delete("/{image_id}", status_code=204, response_class=Response)
async def delete_image(image_id: uuid.UUID, user: User = Depends(require_roles(Role.admin)),
                       db: AsyncSession = Depends(get_db)):
    """Soft delete; the housekeeping job removes objects after the retention period."""
    img = await _get_live(db, image_id)
    img.deleted_at = utcnow()
    audit(db, user, "images.delete", "image", img.id, {"filename": img.filename})
    await db.commit()
    return Response(status_code=204)
