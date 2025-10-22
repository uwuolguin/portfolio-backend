# app/services/image_service.py
import os
import uuid
from io import BytesIO
from typing import Tuple, Dict

import aiohttp
from PIL import Image, UnidentifiedImageError
from fastapi.concurrency import run_in_threadpool

# Config
MAX_SIZE_MB = 5
MAX_BYTES = MAX_SIZE_MB * 1024 * 1024
MAX_WIDTH = 4000
MAX_HEIGHT = 4000
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads/company_images")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_FORMATS = {"JPEG", "PNG"}
ALLOWED_MIME = {"image/jpeg", "image/png"}
EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png"}

# NSFW API
MODERATECONTENT_API_KEY = os.getenv("MODERATE_API_KEY")  # optional
MODERATE_URL = "https://api.moderatecontent.com/moderate/"

class ImageValidationError(ValueError):
    pass


def _ensure_size_limit(file_bytes: bytes):
    if len(file_bytes) > MAX_BYTES:
        raise ImageValidationError(f"Image too large ({len(file_bytes)} bytes)")


def _open_and_verify(file_bytes: bytes) -> Image.Image:
    bio = BytesIO(file_bytes)
    try:
        img = Image.open(bio)
        img.verify()
    except (UnidentifiedImageError, Exception) as e:
        raise ImageValidationError("Not a valid image") from e
    bio.seek(0)
    return Image.open(bio)


def _validate_image(img: Image.Image):
    fmt = img.format or ""
    if fmt.upper() not in ALLOWED_FORMATS:
        raise ImageValidationError(f"Unsupported format: {fmt}")
    if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
        raise ImageValidationError(f"Too large: {img.width}x{img.height}")


def _strip_exif_and_normalize(img: Image.Image, target_format: str) -> BytesIO:
    if target_format == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    out = BytesIO()
    save_kwargs = {}
    if target_format == "JPEG":
        save_kwargs.update({"quality": 90, "optimize": True})
    img.save(out, format=target_format, **save_kwargs)
    out.seek(0)
    return out


async def detect_nsfw_from_url(url: str) -> Dict:
    """
    Calls ModerateContent NSFW API (free, requires key) asynchronously.
    """
    params = {"key": MODERATECONTENT_API_KEY, "url": url}
    async with aiohttp.ClientSession() as session:
        async with session.get(MODERATE_URL, params=params) as resp:
            if resp.status != 200:
                return {"error": f"NSFW API failed: {resp.status}"}
            return await resp.json()


def _store_image_sync(file_bytes: bytes, content_type: str) -> Tuple[str, str]:
    """Synchronous heavy work, offloaded via run_in_threadpool."""
    if content_type not in ALLOWED_MIME:
        raise ImageValidationError("Unsupported content type")
    _ensure_size_limit(file_bytes)

    img = _open_and_verify(file_bytes)
    _validate_image(img)
    fmt = (img.format or "").upper()
    fmt = fmt if fmt in ALLOWED_FORMATS else "JPEG"

    processed_io = _strip_exif_and_normalize(img, fmt)
    ext = EXT_BY_FORMAT.get(fmt, "jpg")
    filename = f"{uuid.uuid4()}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)

    tmp_path = save_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(processed_io.read())
    os.replace(tmp_path, save_path)
    return filename, save_path


async def process_and_store_image_async(file_bytes: bytes, content_type: str, public_url: str = None) -> Dict:
    """
    Async-safe wrapper: process, store, and (optionally) run NSFW detection.
    """
    filename, save_path = await run_in_threadpool(_store_image_sync, file_bytes, content_type)

    nsfw_result = None
    if public_url and MODERATECONTENT_API_KEY:
        nsfw_result = await detect_nsfw_from_url(public_url)

    return {
        "filename": filename,
        "path": save_path,
        "nsfw_check": nsfw_result,
    }
