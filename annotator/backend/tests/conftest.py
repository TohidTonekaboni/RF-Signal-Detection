import io
import os
import tempfile
import uuid
from pathlib import Path

# Environment must be set before the app (and its cached settings) is imported.
_TMP = Path(tempfile.mkdtemp(prefix="annotator-tests-"))
os.environ.update(
    APP_ENV="test",
    # TEST_DATABASE_URL (postgresql+asyncpg://...) runs the same suite against a real Postgres.
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{_TMP / 'test.db'}"),
    JWT_SECRET="test-secret-test-secret-test-secret-123456",
    S3_ENDPOINT="http://minio.internal:9000",
    S3_PUBLIC_ENDPOINT="https://annotator.lan:9443",
    S3_ACCESS_KEY="app",
    S3_SECRET_KEY="app-secret-key",
    MAX_UPLOAD_MB="1",
    LOCKOUT_MAX_FAILURES="5",
)

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from PIL.PngImagePlugin import PngInfo  # noqa: E402
from pwdlib import PasswordHash  # noqa: E402
from pwdlib.hashers.argon2 import Argon2Hasher  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from alembic import command  # noqa: E402
from app.core import security  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.storage.s3 import Storage, get_storage  # noqa: E402

# Cheap argon2 parameters keep the suite fast; production uses pwdlib's recommended settings.
security._hasher = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1),))

# Build the schema with the real migration (also exercises it). Must run outside an event loop.
_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
_cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
command.upgrade(_cfg, "head")


class MemoryStorage(Storage):
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def presign_put(self, bucket, key, content_type, expires):
        return f"https://files.test/put/{bucket}/{key}"

    def presign_get(self, bucket, key, expires):
        return f"https://files.test/get/{bucket}/{key}"

    async def size(self, bucket, key):
        d = self.objects.get((bucket, key))
        return None if d is None else len(d)

    async def get(self, bucket, key):
        return self.objects[(bucket, key)]

    async def put(self, bucket, key, data, content_type):
        self.objects[(bucket, key)] = data

    async def delete(self, bucket, key):
        self.objects.pop((bucket, key), None)

    def browser_upload(self, upload_url: str, data: bytes):
        """Simulate the browser PUTting straight to MinIO."""
        _, _, rest = upload_url.partition("/put/")
        bucket, _, key = rest.partition("/")
        self.objects[(bucket, key)] = data


@pytest.fixture
def storage():
    s = MemoryStorage()
    app.dependency_overrides[get_storage] = lambda: s
    yield s
    app.dependency_overrides.pop(get_storage, None)


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with get_sessionmaker()() as db:
        for table in reversed(Base.metadata.sorted_tables):
            await db.execute(delete(table))
        await db.commit()
    yield


@pytest_asyncio.fixture
async def client(storage):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def make_user(username: str, role: str = Role.annotator.value, password: str = "password123",
                    must_change: bool = False, active: bool = True) -> User:
    async with get_sessionmaker()() as db:
        u = User(username=username, role=role, password_hash=security.hash_password_sync(password),
                 active=active, must_change_password=must_change)
        db.add(u)
        await db.commit()
        return u


async def login(client: httpx.AsyncClient, username: str, password: str = "password123") -> dict[str, str]:
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin(client):
    await make_user("admin", Role.admin.value)
    return await login(client, "admin")


@pytest_asyncio.fixture
async def annotator(client):
    await make_user("ann", Role.annotator.value)
    return await login(client, "ann")


@pytest_asyncio.fixture
async def reviewer(client):
    await make_user("rev", Role.reviewer.value)
    return await login(client, "rev")


def png_bytes(seed: int = 0, size=(64, 32), mode="RGB", info: dict | None = None) -> bytes:
    im = PILImage.new(mode, size)
    px = im.load()
    for x in range(size[0]):
        for y in range(size[1]):
            v = (x * 7 + y * 3 + seed * 41) % 256
            px[x, y] = (v, (v + seed) % 256, 255 - v) if mode == "RGB" else v
    pnginfo = None
    if info:
        pnginfo = PngInfo()
        for k, v in info.items():
            pnginfo.add_text(k, str(v))
    out = io.BytesIO()
    im.save(out, format="PNG", pnginfo=pnginfo)
    return out.getvalue()


async def upload_image(client, storage, headers, seed: int = 0, filename: str | None = None, **kw) -> dict:
    data = png_bytes(seed, **kw)
    r = await client.post("/api/images/presign", headers=headers,
                          json={"filename": filename or f"cap_{seed}.png", "content_type": "image/png", "size": len(data)})
    assert r.status_code == 201, r.text
    storage.browser_upload(r.json()["upload_url"], data)
    r2 = await client.post(f"/api/images/{r.json()['image_id']}/complete", headers=headers)
    assert r2.status_code == 200, r2.text
    return r2.json()


def new_id() -> str:
    return str(uuid.uuid4())
