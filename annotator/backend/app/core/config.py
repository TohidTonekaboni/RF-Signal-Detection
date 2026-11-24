from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. Names match the variables set in docker-compose.yml."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_host: str = "localhost"
    log_level: str = "info"

    database_url: str = "postgresql+asyncpg://annotator:annotator@localhost:5432/annotator"
    # Sync-style DSN for procrastinate; derived from database_url when empty.
    procrastinate_dsn: str = ""

    jwt_secret: str = Field(default="dev-only-change-me-dev-only-change-me")
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    refresh_grace_seconds: int = 10

    lockout_max_failures: int = 5
    lockout_ip_max_failures: int = 30
    lockout_window_minutes: int = 15

    s3_endpoint: str = "http://localhost:9000"
    # Host the BROWSER uses; presigned URLs are signed for this host.
    s3_public_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_images: str = "images"
    s3_bucket_thumbs: str = "thumbs"
    s3_bucket_exports: str = "exports"
    presign_get_seconds: int = 3600
    presign_put_seconds: int = 900

    max_upload_mb: int = 100
    max_image_pixels: int = 100_000_000
    thumb_max_px: int = 480

    pending_upload_ttl_hours: int = 24
    deleted_retention_days: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def worker_dsn(self) -> str:
        return self.procrastinate_dsn or self.database_url.replace("postgresql+asyncpg", "postgresql")

    def validate_for_runtime(self) -> None:
        if self.is_production and (len(self.jwt_secret) < 32 or self.jwt_secret.startswith("dev-only")):
            raise RuntimeError("JWT_SECRET must be set to a random value of at least 32 characters in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
