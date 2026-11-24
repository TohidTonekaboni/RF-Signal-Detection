"""procrastinate app (Postgres-backed job queue; no Redis).

CLI used by docker-compose:
    procrastinate --app=app.workers.app schema --apply
    procrastinate --app=app.workers.app worker --queues default,exports
"""
import procrastinate

from app.core.config import get_settings

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=get_settings().worker_dsn),
    import_paths=["app.workers.tasks"],
)
