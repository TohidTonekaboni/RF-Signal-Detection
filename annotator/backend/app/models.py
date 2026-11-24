from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Role(enum.StrEnum):
    admin = "admin"
    annotator = "annotator"
    reviewer = "reviewer"


class ImageStatus(enum.StrEnum):
    pending = "pending"  # presigned, bytes not yet verified
    ready = "ready"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class RefreshSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # set only by refresh rotation
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_username_at", "username", "at"), Index("ix_login_attempts_ip_at", "ip", "at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean)


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (Index("ix_images_created_at", "created_at"), Index("ix_images_sha256", "sha256"))
    id: Mapped[uuid.UUID] = _uuid_pk()
    filename: Mapped[str] = mapped_column(String(255))  # original name; display only, never used as a storage key
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    thumb_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict] = mapped_column(JsonType, default=dict)  # {duration_s, bandwidth_hz, center_freq_hz}
    status: Mapped[str] = mapped_column(String(16), default=ImageStatus.pending.value)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    uploader: Mapped[User | None] = relationship(lazy="joined")


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    classes: Mapped[list[ClassDef]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ClassDef.position", lazy="selectin")


class ClassDef(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("experiment_id", "name"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(7))
    position: Mapped[int] = mapped_column(Integer, default=0)

    experiment: Mapped[Experiment] = relationship(back_populates="classes")


class ExperimentImage(Base):
    """Membership of an image in an experiment + that image's annotation state (version = optimistic lock)."""

    __tablename__ = "experiment_images"
    __table_args__ = (UniqueConstraint("experiment_id", "image_id"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    image_labels: Mapped[list] = mapped_column(JsonType, default=list)  # class names
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    image: Mapped[Image] = relationship(lazy="joined")


class BoundingBox(Base):
    __tablename__ = "bounding_boxes"
    __table_args__ = (
        UniqueConstraint("experiment_image_id", "box_id"),
        CheckConstraint("x >= 0 AND y >= 0 AND w > 0 AND h > 0 AND x + w <= 1.000001 AND y + h <= 1.000001",
                        name="box_in_bounds"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    experiment_image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiment_images.id", ondelete="CASCADE"), index=True)
    box_id: Mapped[str] = mapped_column(String(40))  # client-generated id, echoed back to the UI
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="RESTRICT"), index=True)
    x: Mapped[float] = mapped_column(Float)  # normalized 0..1
    y: Mapped[float] = mapped_column(Float)
    w: Mapped[float] = mapped_column(Float)
    h: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", "at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor: Mapped[str] = mapped_column(String(64))  # username snapshot; survives user deletion
    action: Mapped[str] = mapped_column(String(128))
    entity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
