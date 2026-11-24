import io
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_sessionmaker
from app.db.types import utcnow
from app.models import Image, ImageStatus, LoginAttempt, RefreshSession, Role, User
from app.services.housekeeping import run_housekeeping
from app.services.imaging import InvalidImage, process_image
from app.storage.s3 import S3Storage
from tests.conftest import MemoryStorage, png_bytes


async def test_health_endpoints(client):
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).json() == {"status": "ready"}


async def test_error_envelope_for_unknown_route_and_method(client, admin):
    r = await client.get("/api/nope", headers=admin)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    r = await client.delete("/api/auth/me", headers=admin)
    assert r.status_code == 405 and r.json()["code"] == "method_not_allowed"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-request-id"]


def test_migration_matches_models():
    """The hand-written Alembic migration must describe exactly what the models define."""
    url = get_settings().database_url.replace("sqlite+aiosqlite", "sqlite").replace("+asyncpg", "+psycopg")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], diff


def test_presigned_urls_target_the_public_host_and_are_signed():
    s = S3Storage(get_settings())
    put = urlparse(s.presign_put("images", "2025/11/x.png", "image/png", 900))
    assert put.scheme == "https" and put.netloc == "annotator.lan:9443" and put.path == "/images/2025/11/x.png"
    q = parse_qs(put.query)
    assert q["X-Amz-Expires"] == ["900"] and q["X-Amz-Signature"] and "content-type" in q["X-Amz-SignedHeaders"][0]
    get = urlparse(s.presign_get("thumbs", "k.jpg", 60))
    assert get.netloc == "annotator.lan:9443" and "minio.internal" not in get.geturl()


def test_process_image_png_jpeg_and_16bit():
    from PIL import Image as P
    p = process_image(png_bytes(1, size=(300, 100)))
    assert (p.width, p.height, p.content_type) == (300, 100, "image/png") and P.open(io.BytesIO(p.thumb)).size == (300, 100)
    big = process_image(png_bytes(2, size=(2000, 1000)))
    assert max(P.open(io.BytesIO(big.thumb)).size) == get_settings().thumb_max_px
    buf = io.BytesIO(); P.new("RGB", (10, 10), "red").save(buf, format="JPEG")
    assert process_image(buf.getvalue()).content_type == "image/jpeg"
    buf = io.BytesIO(); P.new("I;16", (10, 10), 40000).save(buf, format="PNG")
    assert process_image(buf.getvalue()).width == 10
    buf = io.BytesIO(); P.new("L", (8, 8)).save(buf, format="PNG")
    assert process_image(buf.getvalue()).height == 8


def test_process_image_rejections(monkeypatch):
    for bad in (b"", b"not an image", png_bytes()[:40]):
        with pytest.raises(InvalidImage):
            process_image(bad)
    monkeypatch.setattr(get_settings(), "max_image_pixels", 100)
    with pytest.raises(InvalidImage):  # decompression-bomb guard
        process_image(png_bytes(size=(64, 32)))


async def test_housekeeping_purges_stale_data_only():
    storage = MemoryStorage()
    s = get_settings()
    old, fresh = utcnow() - timedelta(hours=s.pending_upload_ttl_hours + 1), utcnow()
    async with get_sessionmaker()() as db:
        u = User(username="u", role=Role.annotator.value, password_hash="x", active=True, must_change_password=False)
        db.add(u); await db.flush()
        mk = lambda key, status, created, deleted=None: Image(  # noqa: E731
            filename=key, storage_key=key, content_type="image/png", size=1, status=status, uploaded_by=u.id,
            created_at=created, deleted_at=deleted, meta={}, thumb_key=key + ".t")
        db.add_all([mk("stale-pending", ImageStatus.pending.value, old), mk("fresh-pending", ImageStatus.pending.value, fresh),
                    mk("old-deleted", ImageStatus.ready.value, old, utcnow() - timedelta(days=s.deleted_retention_days + 1)),
                    mk("recent-deleted", ImageStatus.ready.value, old, utcnow() - timedelta(days=1)),
                    mk("live", ImageStatus.ready.value, old)])
        db.add_all([RefreshSession(user_id=u.id, token_hash="a", expires_at=utcnow() - timedelta(days=30)),
                    RefreshSession(user_id=u.id, token_hash="b", expires_at=utcnow() + timedelta(days=1)),
                    LoginAttempt(username="u", at=utcnow() - timedelta(days=30), success=False),
                    LoginAttempt(username="u", at=utcnow(), success=False)])
        await db.commit()
        for k in ("stale-pending", "fresh-pending", "old-deleted", "recent-deleted", "live"):
            storage.objects[("images", k)] = b"x"; storage.objects[("thumbs", k + ".t")] = b"x"
        out = await run_housekeeping(db, storage)
        left = {i.storage_key for i in (await db.scalars(select(Image))).unique()}
    assert out == {"sessions": 1, "attempts": 1, "pending_images": 1, "deleted_images": 1}
    assert left == {"fresh-pending", "recent-deleted", "live"}
    assert {k for b, k in storage.objects if b == "images"} == left


async def test_cli_create_admin_and_reset_password(client):
    from app import cli
    await cli.create_admin("Root", "supersecret1")
    r = await client.post("/api/auth/login", json={"username": "root", "password": "supersecret1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin" and not r.json()["user"]["must_change_password"]
    with pytest.raises(SystemExit):
        await cli.create_admin("root", "supersecret1")  # exists
    with pytest.raises(Exception):
        await cli.create_admin("weak", "short")
    await cli.reset_password("root", "recovery-pass1")
    r = await client.post("/api/auth/login", json={"username": "root", "password": "recovery-pass1"})
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    with pytest.raises(SystemExit):
        await cli.reset_password("ghost", "recovery-pass1")


def test_production_refuses_weak_jwt_secret(monkeypatch):
    from app.core.config import Settings
    with pytest.raises(RuntimeError):
        Settings(app_env="production", jwt_secret="short").validate_for_runtime()
    with pytest.raises(RuntimeError):
        Settings(app_env="production", jwt_secret="dev-only-change-me-dev-only-change-me").validate_for_runtime()
    Settings(app_env="production", jwt_secret="x" * 40).validate_for_runtime()
