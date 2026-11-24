import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, exists, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import active_user, require_roles
from app.core.errors import AppError
from app.db.session import get_db
from app.models import BoundingBox, ClassDef, Experiment, ExperimentImage, Image, ImageStatus, Role, User
from app.schemas import (
    AddImagesIn,
    ClassOut,
    ClassStat,
    ExperimentCreate,
    ExperimentImageOut,
    ExperimentOut,
    ExperimentUpdate,
    StatsOut,
)
from app.services.audit import audit
from app.services.serialize import image_out
from app.storage.s3 import Storage, get_storage

router = APIRouter(prefix="/experiments", tags=["experiments"])
admin_only = require_roles(Role.admin)


def _live_image():
    return and_(Image.status == ImageStatus.ready.value, Image.deleted_at.is_(None))


async def _get(db: AsyncSession, exp_id: uuid.UUID) -> Experiment:
    exp = await db.get(Experiment, exp_id)
    if exp is None:
        raise AppError(404, "not_found")
    return exp


async def _counts(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """{experiment_id: (image_count, annotated_count)} over live images only."""
    if not ids:
        return {}
    has_box = exists().where(BoundingBox.experiment_image_id == ExperimentImage.id)
    rows = await db.execute(
        select(ExperimentImage.experiment_id, func.count(), func.sum(case((has_box, 1), else_=0)))
        .join(Image, Image.id == ExperimentImage.image_id)
        .where(ExperimentImage.experiment_id.in_(ids), _live_image())
        .group_by(ExperimentImage.experiment_id))
    return {r[0]: (r[1], int(r[2] or 0)) for r in rows}


def _out(exp: Experiment, counts: dict) -> ExperimentOut:
    n, a = counts.get(exp.id, (0, 0))
    return ExperimentOut(id=exp.id, name=exp.name, description=exp.description, created_at=exp.created_at,
                         classes=[ClassOut.model_validate(c) for c in exp.classes], image_count=n, annotated_count=a)


async def _add_images(db: AsyncSession, exp_id: uuid.UUID, image_ids: list[uuid.UUID] | None) -> int:
    existing = select(ExperimentImage.image_id).where(ExperimentImage.experiment_id == exp_id)
    q = select(Image.id).where(_live_image(), Image.id.not_in(existing))
    if image_ids is not None:
        q = q.where(Image.id.in_(image_ids))
    ids = (await db.scalars(q)).all()
    if ids:
        await db.execute(insert(ExperimentImage), [{"id": uuid.uuid4(), "experiment_id": exp_id, "image_id": i,
                                                    "version": 1, "image_labels": []} for i in ids])
    return len(ids)


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(_: User = Depends(active_user), db: AsyncSession = Depends(get_db)):
    exps = (await db.scalars(select(Experiment).order_by(Experiment.created_at.desc()))).all()
    counts = await _counts(db, [e.id for e in exps])
    return [_out(e, counts) for e in exps]


@router.post("", response_model=ExperimentOut, status_code=201)
async def create_experiment(body: ExperimentCreate, user: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    exp = Experiment(name=body.name, description=body.description, created_by=user.id,
                     classes=[ClassDef(name=c.name, color=c.color, position=i) for i, c in enumerate(body.classes)])
    db.add(exp)
    await db.flush()
    added = await _add_images(db, exp.id, None)  # the UI has no image picker yet: start with the whole library
    audit(db, user, "experiments.create", "experiment", exp.id, {"name": exp.name, "images": added})
    await db.commit()
    return _out(exp, await _counts(db, [exp.id]))


@router.get("/{exp_id}", response_model=ExperimentOut)
async def get_experiment(exp_id: uuid.UUID, _: User = Depends(active_user), db: AsyncSession = Depends(get_db)):
    exp = await _get(db, exp_id)
    return _out(exp, await _counts(db, [exp.id]))


@router.put("/{exp_id}", response_model=ExperimentOut)
async def update_experiment(exp_id: uuid.UUID, body: ExperimentUpdate, user: User = Depends(admin_only),
                            db: AsyncSession = Depends(get_db)):
    exp = await _get(db, exp_id)
    if body.name is not None:
        exp.name = body.name.strip()
    if body.description is not None:
        exp.description = body.description
    if body.classes is not None:
        current = {c.id: c for c in exp.classes}
        for c in body.classes:
            if c.id is not None and c.id not in current:
                raise AppError(422, "validation_error", "Unknown class id")
        keep = {c.id for c in body.classes if c.id is not None}
        for cid, cls in current.items():
            if cid not in keep:
                used = await db.scalar(select(func.count()).select_from(BoundingBox).where(BoundingBox.class_id == cid))
                if used:
                    raise AppError(409, "class_in_use", f"Class '{cls.name}' has annotations and cannot be removed")
                exp.classes.remove(cls)
        # Two-phase rename avoids transient unique(experiment_id, name) clashes when names are swapped.
        for i, c in enumerate(body.classes):
            if c.id is not None:
                cls = current[c.id]
                cls.name, cls.color, cls.position = f"~tmp~{cls.id}", c.color, i  # 41 chars, fits String(50)
        await db.flush()
        for i, c in enumerate(body.classes):
            if c.id is None:
                exp.classes.append(ClassDef(name=c.name, color=c.color, position=i))
            else:
                current[c.id].name = c.name
    try:
        audit(db, user, "experiments.update", "experiment", exp.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "conflict", "Duplicate class name") from None
    await db.refresh(exp)
    return _out(exp, await _counts(db, [exp.id]))


@router.post("/{exp_id}/images", status_code=200)
async def add_images(exp_id: uuid.UUID, body: AddImagesIn, user: User = Depends(admin_only),
                     db: AsyncSession = Depends(get_db)):
    exp = await _get(db, exp_id)
    if not body.all and not body.image_ids:
        raise AppError(422, "validation_error", "Provide image_ids or all=true")
    added = await _add_images(db, exp.id, None if body.all else body.image_ids)
    audit(db, user, "experiments.add_images", "experiment", exp.id, {"added": added})
    await db.commit()
    return {"added": added}


@router.get("/{exp_id}/stats", response_model=StatsOut)
async def stats(exp_id: uuid.UUID, _: User = Depends(active_user), db: AsyncSession = Depends(get_db)):
    exp = await _get(db, exp_id)
    n, annotated = (await _counts(db, [exp.id])).get(exp.id, (0, 0))
    rows = await db.execute(
        select(BoundingBox.class_id, func.count())
        .join(ExperimentImage, ExperimentImage.id == BoundingBox.experiment_image_id)
        .join(Image, Image.id == ExperimentImage.image_id)
        .where(ExperimentImage.experiment_id == exp.id, _live_image()).group_by(BoundingBox.class_id))
    by_class = {r[0]: r[1] for r in rows}
    return StatsOut(total=n, annotated=annotated, per_class=[
        ClassStat(class_id=c.id, name=c.name, color=c.color, count=by_class.get(c.id, 0)) for c in exp.classes])


@router.get("/{exp_id}/images")
async def list_experiment_images(exp_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(1000, ge=1, le=5000),
                                 _: User = Depends(active_user), db: AsyncSession = Depends(get_db),
                                 storage: Storage = Depends(get_storage)):
    await _get(db, exp_id)
    base = (ExperimentImage.experiment_id == exp_id, _live_image())
    total = await db.scalar(select(func.count()).select_from(ExperimentImage)
                            .join(Image, Image.id == ExperimentImage.image_id).where(*base))
    has_box = exists().where(BoundingBox.experiment_image_id == ExperimentImage.id).label("annotated")
    rows = (await db.execute(
        select(ExperimentImage, has_box).join(Image, Image.id == ExperimentImage.image_id).where(*base)
        .order_by(Image.created_at.desc(), Image.id).offset((page - 1) * page_size).limit(page_size))).unique().all()
    items: list[ExperimentImageOut] = [image_out(r[0].image, storage, annotated=bool(r[1])) for r in rows]
    return {"items": items, "total": total or 0}
