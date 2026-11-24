"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_login_at", TS),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.Column("rotated_at", TS),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("at", TS, nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_login_attempts_username_at", "login_attempts", ["username", "at"])
    op.create_index("ix_login_attempts_ip_at", "login_attempts", ["ip", "at"])
    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("thumb_key", sa.String(255)),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("meta", JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("deleted_at", TS),
    )
    op.create_index("ix_images_created_at", "images", ["created_at"])
    op.create_index("ix_images_sha256", "images", ["sha256"])
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "classes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("experiment_id", sa.Uuid(), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("experiment_id", "name"),
    )
    op.create_index("ix_classes_experiment_id", "classes", ["experiment_id"])
    op.create_table(
        "experiment_images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("experiment_id", sa.Uuid(), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", sa.Uuid(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("image_labels", JSON, nullable=False),
        sa.Column("updated_at", TS),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("experiment_id", "image_id"),
    )
    op.create_index("ix_experiment_images_experiment_id", "experiment_images", ["experiment_id"])
    op.create_index("ix_experiment_images_image_id", "experiment_images", ["image_id"])
    op.create_table(
        "bounding_boxes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("experiment_image_id", sa.Uuid(), sa.ForeignKey("experiment_images.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("box_id", sa.String(40), nullable=False),
        sa.Column("class_id", sa.Uuid(), sa.ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("w", sa.Float(), nullable=False),
        sa.Column("h", sa.Float(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("experiment_image_id", "box_id"),
        sa.CheckConstraint("x >= 0 AND y >= 0 AND w > 0 AND h > 0 AND x + w <= 1.000001 AND y + h <= 1.000001",
                           name="box_in_bounds"),
    )
    op.create_index("ix_bounding_boxes_experiment_image_id", "bounding_boxes", ["experiment_image_id"])
    op.create_index("ix_bounding_boxes_class_id", "bounding_boxes", ["class_id"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", TS, nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(32)),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("detail", JSON),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    for t in ("audit_log", "bounding_boxes", "experiment_images", "classes", "experiments", "images",
              "login_attempts", "sessions", "users"):
        op.drop_table(t)
