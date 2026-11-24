from app.core.config import get_settings
from app.models import Image
from app.schemas import ExperimentImageOut, ImageOut
from app.storage.s3 import Storage


def image_out(img: Image, storage: Storage, annotated: bool | None = None) -> ImageOut | ExperimentImageOut:
    s = get_settings()
    url = storage.presign_get(s.s3_bucket_images, img.storage_key, s.presign_get_seconds)
    thumb = (storage.presign_get(s.s3_bucket_thumbs, img.thumb_key, s.presign_get_seconds)
             if img.thumb_key else url)
    data = dict(id=img.id, filename=img.filename, url=url, thumb_url=thumb, width=img.width, height=img.height,
                size=img.size, content_type=img.content_type, created_at=img.created_at, meta=img.meta or {},
                uploaded_by=img.uploader.username if img.uploader else None)
    return ExperimentImageOut(**data, annotated=annotated) if annotated is not None else ImageOut(**data)
