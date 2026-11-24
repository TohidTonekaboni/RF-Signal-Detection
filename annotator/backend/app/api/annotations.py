import re
import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import active_user, require_roles
from app.core.errors import AppError
from app.db.session import get_db
from app.db.types import utcnow
from app.models import BoundingBox, Experiment, ExperimentImage, Image, Role, User
from app.schemas import AnnotationsIn, AnnotationsOut, BoxIO
from app.services.audit import audit

router = APIRouter(prefix="/experiments/{exp_id}/images/{image_id}/annotations", tags=["annotations"])
editors = require_roles(Role.admin, Role.annotator)  # reviewers are read-only here


def _parse_version(if_match: str | None) -> int:
    if if_match is None:
        raise AppError(428, "precondition_required", "If-Match header with the current version is required")
    m = re.fullmatch(r'\s*(?:W/)?"?(\d+)"?\s*', if_match)
    if not m:
        raise AppError(400, "validation_error", "If-Match must be an integer version")
    return int(m.group(1))


async def _member(db: AsyncSession, exp_id: uuid.UUID, image_id: uuid.UUID) -> ExperimentImage:
    ei = await db.scalar(select(ExperimentImage).join(Image, Image.id == ExperimentImage.image_id).where(
        ExperimentImage.experiment_id == exp_id, ExperimentImage.image_id == image_id, Image.deleted_at.is_(None)))
    if ei is None:
        raise AppError(404, "not_found")
    return ei


async def _snapshot(db: AsyncSession, ei: ExperimentImage) -> AnnotationsOut:
    rows = (await db.scalars(select(BoundingBox).where(BoundingBox.experiment_image_id == ei.id)
                             .order_by(BoundingBox.position))).all()
    return AnnotationsOut(
        boxes=[BoxIO(id=b.box_id, class_id=b.class_id, x=b.x, y=b.y, w=b.w, h=b.h) for b in rows],
        image_labels=list(ei.image_labels or []), version=ei.version)


@router.get("", response_model=AnnotationsOut)
async def get_annotations(exp_id: uuid.UUID, image_id: uuid.UUID, response: Response, _: User = Depends(active_user),
                          db: AsyncSession = Depends(get_db)):
    ei = await _member(db, exp_id, image_id)
    response.headers["ETag"] = f'"{ei.version}"'
    response.headers["Cache-Control"] = "no-store"
    return await _snapshot(db, ei)


@router.put("", response_model=AnnotationsOut)
async def save_annotations(exp_id: uuid.UUID, image_id: uuid.UUID, body: AnnotationsIn, response: Response,
                           if_match: str | None = Header(None), user: User = Depends(editors),
                           db: AsyncSession = Depends(get_db)):
    """Replace the full annotation set for one image. Optimistic concurrency via If-Match: <version>."""
    expected = _parse_version(if_match)
    ei = await _member(db, exp_id, image_id)
    ei_id = ei.id  # plain value: ORM objects are expired by rollback
    exp = await db.get(Experiment, exp_id)
    class_ids = {c.id for c in exp.classes}
    class_names = {c.name for c in exp.classes}
    if any(b.class_id not in class_ids for b in body.boxes):
        raise AppError(422, "validation_error", "Box references a class outside this experiment")
    if any(label not in class_names for label in body.image_labels):
        raise AppError(422, "validation_error", "Image label is not a class of this experiment")
    if len({b.id for b in body.boxes}) != len(body.boxes):
        raise AppError(422, "validation_error", "Duplicate box ids")

    # Compare-and-swap on the version: of two concurrent saves, exactly one wins.
    res = await db.execute(update(ExperimentImage)
                           .where(ExperimentImage.id == ei.id, ExperimentImage.version == expected)
                           .values(version=ExperimentImage.version + 1, image_labels=list(body.image_labels),
                                   updated_at=utcnow(), updated_by=user.id))
    if res.rowcount != 1:
        await db.rollback()
        raise AppError(409, "conflict", "These annotations were changed by someone else",
                       {"current_version": (await _current_version(db, ei_id))})
    await db.execute(delete(BoundingBox).where(BoundingBox.experiment_image_id == ei.id))
    db.add_all(BoundingBox(experiment_image_id=ei.id, box_id=b.id, class_id=b.class_id, x=b.x, y=b.y, w=b.w, h=b.h,
                           position=i, created_by=user.id) for i, b in enumerate(body.boxes))
    audit(db, user, f"annotations.save {image_id}", "experiment_image", ei.id,
          {"experiment_id": str(exp_id), "boxes": len(body.boxes), "labels": len(body.image_labels)})
    await db.commit()
    await db.refresh(ei)
    response.headers["ETag"] = f'"{ei.version}"'
    return await _snapshot(db, ei)


async def _current_version(db: AsyncSession, ei_id: uuid.UUID) -> int | None:
    return await db.scalar(select(ExperimentImage.version).where(ExperimentImage.id == ei_id))
