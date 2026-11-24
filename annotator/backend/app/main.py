import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api import annotations, audit, auth, experiments, health, images, users
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import setup_logging
from app.db.session import dispose_engine

log = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    s.validate_for_runtime()
    setup_logging(s.log_level)
    docs = not s.is_production  # no public API docs in production
    app = FastAPI(title="Spectrogram Annotator API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if docs else None)
    install_error_handlers(app)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.url.path != "/healthz":
            log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                                       "status": response.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1)})
        return response

    app.include_router(health.router)  # /healthz, /readyz (outside /api: used by container healthchecks)
    for r in (auth, users, images, experiments, annotations, audit):
        app.include_router(r.router, prefix="/api")
    return app


app = create_app()
