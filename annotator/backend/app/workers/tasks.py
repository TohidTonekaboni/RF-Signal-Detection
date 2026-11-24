from app.db.session import get_sessionmaker
from app.services.housekeeping import run_housekeeping
from app.storage.s3 import get_storage
from app.workers import app


@app.periodic(cron="17 3 * * *")  # daily, 03:17
@app.task(name="housekeeping", queue="default", queueing_lock="housekeeping")
async def housekeeping(timestamp: int) -> dict:
    """Purge expired sessions/login attempts, abandoned uploads and long-deleted images."""
    async with get_sessionmaker()() as db:
        return await run_housekeeping(db, get_storage())
