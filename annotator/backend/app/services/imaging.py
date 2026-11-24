"""Image validation + thumbnailing. CPU-bound: call through asyncio.to_thread."""
import io
from dataclasses import dataclass, field

from PIL import Image as PILImage

from app.core.config import get_settings

ALLOWED = {"PNG": "image/png", "JPEG": "image/jpeg"}
EXT = {"image/png": "png", "image/jpeg": "jpg"}
META_KEYS = ("duration_s", "bandwidth_hz", "center_freq_hz")


class InvalidImage(Exception):
    pass


@dataclass
class Processed:
    width: int
    height: int
    content_type: str
    thumb: bytes
    meta: dict[str, float] = field(default_factory=dict)


def _meta_from_info(info: dict) -> dict[str, float]:
    """PNG tEXt chunks named duration_s / bandwidth_hz / center_freq_hz are picked up when present."""
    meta: dict[str, float] = {}
    for k in META_KEYS:
        try:
            v = float(info[k])
        except (KeyError, TypeError, ValueError):
            continue
        if v > 0 or (k == "center_freq_hz" and v == 0):
            meta[k] = v
    return meta


def process_image(data: bytes) -> Processed:
    s = get_settings()
    PILImage.MAX_IMAGE_PIXELS = s.max_image_pixels
    try:
        with PILImage.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            if fmt not in ALLOWED:
                raise InvalidImage(f"unsupported format {fmt}")
            probe.verify()  # structural check; image must be re-opened afterwards
        with PILImage.open(io.BytesIO(data)) as im:
            im.load()  # full decode: catches truncated/corrupt data
            width, height = im.size
            if width < 1 or height < 1:
                raise InvalidImage("empty image")
            meta = _meta_from_info(im.info)
            thumb_src = im
            if im.mode in ("I;16", "I;16L", "I;16B", "I"):
                thumb_src = im.point(lambda p: p * (1 / 256)).convert("L")
            thumb = thumb_src.convert("RGB")
            thumb.thumbnail((s.thumb_max_px, s.thumb_max_px))
            out = io.BytesIO()
            thumb.save(out, format="JPEG", quality=85, optimize=True)
    except InvalidImage:
        raise
    except Exception as e:  # PIL raises many types (UnidentifiedImageError, DecompressionBombError, OSError, ...)
        raise InvalidImage(str(e)) from e
    return Processed(width, height, ALLOWED[fmt], out.getvalue(), meta)
