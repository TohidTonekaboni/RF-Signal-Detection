import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Role

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class Msg(BaseModel):
    ok: bool = True


# ---- auth / users
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    role: Role
    active: bool
    must_change_password: bool


class TokenOut(BaseModel):
    access_token: str
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    role: Role
    password: str = Field(min_length=8, max_length=128)


class UserPatch(BaseModel):
    active: bool | None = None
    role: Role | None = None


class TempPasswordOut(BaseModel):
    temporary_password: str


# ---- images
class ImageOut(BaseModel):
    id: uuid.UUID
    filename: str
    url: str
    thumb_url: str
    width: int | None
    height: int | None
    size: int
    content_type: str
    created_at: datetime
    meta: dict[str, Any]
    uploaded_by: str | None = None


class ExperimentImageOut(ImageOut):
    annotated: bool = False


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class PresignIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size: int = Field(gt=0)


class PresignOut(BaseModel):
    image_id: uuid.UUID
    upload_url: str


class ImageMetaIn(BaseModel):
    """Physical metadata used by the workspace HUD to map pixels → seconds/Hz."""

    duration_s: float | None = Field(default=None, gt=0)
    bandwidth_hz: float | None = Field(default=None, gt=0)
    center_freq_hz: float | None = Field(default=None, ge=0)


class ImagePatch(BaseModel):
    meta: ImageMetaIn


# ---- experiments
class ClassIn(BaseModel):
    id: uuid.UUID | None = None  # present when editing an existing class
    name: str = Field(min_length=1, max_length=50)
    color: str

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v: str) -> str:
        if not COLOR_RE.match(v):
            raise ValueError("color must be #RRGGBB")
        return v.upper()


def _unique_names(classes: list[ClassIn]) -> list[ClassIn]:
    names = [c.name.lower() for c in classes]
    if len(set(names)) != len(names):
        raise ValueError("duplicate class names")
    return classes


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    classes: list[ClassIn] = Field(min_length=1, max_length=64)

    _u = field_validator("classes")(_unique_names)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    classes: list[ClassIn] | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("classes")
    @classmethod
    def _u(cls, v):
        return _unique_names(v) if v else v


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str


class ExperimentOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    classes: list[ClassOut]
    image_count: int = 0
    annotated_count: int = 0


class AddImagesIn(BaseModel):
    image_ids: list[uuid.UUID] | None = None
    all: bool = False


class ClassStat(BaseModel):
    class_id: uuid.UUID
    name: str
    color: str
    count: int


class StatsOut(BaseModel):
    total: int
    annotated: int
    per_class: list[ClassStat]


# ---- annotations
EPS = 1e-6


class BoxIO(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    class_id: uuid.UUID
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside(self):
        if self.x + self.w > 1 + EPS or self.y + self.h > 1 + EPS:
            raise ValueError("box exceeds image bounds")
        return self


class AnnotationsIn(BaseModel):
    boxes: list[BoxIO] = Field(max_length=2000)
    image_labels: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("image_labels")
    @classmethod
    def _labels(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v) or any(not s or len(s) > 50 for s in v):
            raise ValueError("invalid image_labels")
        return v


class AnnotationsOut(BaseModel):
    boxes: list[BoxIO]
    image_labels: list[str]
    version: int


# ---- audit
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    at: datetime
    actor: str
    action: str
    entity: str | None = None
    entity_id: str | None = None
