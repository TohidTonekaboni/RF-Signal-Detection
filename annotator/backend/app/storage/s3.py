import asyncio
from abc import ABC, abstractmethod

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import Settings


class Storage(ABC):
    """Object-storage abstraction. MinIO today; any S3-compatible store works unchanged."""

    @abstractmethod
    def presign_put(self, bucket: str, key: str, content_type: str, expires: int) -> str: ...

    @abstractmethod
    def presign_get(self, bucket: str, key: str, expires: int) -> str: ...

    @abstractmethod
    async def size(self, bucket: str, key: str) -> int | None:
        """Object size in bytes, or None if it does not exist."""

    @abstractmethod
    async def get(self, bucket: str, key: str) -> bytes: ...

    @abstractmethod
    async def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def delete(self, bucket: str, key: str) -> None: ...


class S3Storage(Storage):
    def __init__(self, s: Settings):
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"},
                     retries={"max_attempts": 3}, connect_timeout=5, read_timeout=60)
        common = dict(aws_access_key_id=s.s3_access_key, aws_secret_access_key=s.s3_secret_key,
                      region_name="us-east-1", config=cfg)
        # `internal` talks to MinIO on the private network; `public` only signs URLs for the browser's host.
        self._internal = boto3.client("s3", endpoint_url=s.s3_endpoint, **common)
        self._public = boto3.client("s3", endpoint_url=s.s3_public_endpoint or s.s3_endpoint, **common)

    def presign_put(self, bucket, key, content_type, expires):
        return self._public.generate_presigned_url(
            "put_object", Params={"Bucket": bucket, "Key": key, "ContentType": content_type}, ExpiresIn=expires)

    def presign_get(self, bucket, key, expires):
        return self._public.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires)

    async def size(self, bucket, key):
        def _head():
            try:
                return self._internal.head_object(Bucket=bucket, Key=key)["ContentLength"]
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                    return None
                raise
        return await asyncio.to_thread(_head)

    async def get(self, bucket, key):
        def _get():
            return self._internal.get_object(Bucket=bucket, Key=key)["Body"].read()
        return await asyncio.to_thread(_get)

    async def put(self, bucket, key, data, content_type):
        await asyncio.to_thread(self._internal.put_object, Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    async def delete(self, bucket, key):
        await asyncio.to_thread(self._internal.delete_object, Bucket=bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    from app.core.config import get_settings

    global _storage
    if _storage is None:
        _storage = S3Storage(get_settings())
    return _storage
