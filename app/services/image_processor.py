import os
import uuid
from io import BytesIO
from typing import Dict, Optional, Tuple
from pathlib import Path

import aiohttp
from PIL import Image, UnidentifiedImageError
from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------
MAX_SIZE_BYTES = settings.max_file_size
MAX_WIDTH = 4000
MAX_HEIGHT = 4000
ALLOWED_FORMATS = {"JPEG", "PNG"}
ALLOWED_MIME = set(settings.allowed_file_types)
EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png"}
DEEPAI_API_KEY = settings.deepai_api_key


class ImageValidationError(ValueError):
    """Raised when the uploaded image fails validation."""


class ImageProcessor:
    """Handles validation, sanitization, optimization, and DeepAI NSFW checks."""

    # -----------------------------
    # Core validation
    # -----------------------------
    @staticmethod
    def _ensure_size_limit(file_bytes: bytes) -> None:
        if len(file_bytes) > MAX_SIZE_BYTES:
            raise ImageValidationError(
                f"Image too large ({len(file_bytes)/1_048_576:.2f} MB), limit {MAX_SIZE_BYTES/1_048_576:.2f} MB"
            )

    @staticmethod
    def _open_and_verify(file_bytes: bytes) -> Image.Image:
        try:
            with Image.open(BytesIO(file_bytes)) as img:
                img.load()
                return img.copy()
        except UnidentifiedImageError:
            raise ImageValidationError("Invalid image format or corrupted image")

    @staticmethod
    def _validate_format(img: Image.Image) -> None:
        fmt = (img.format or "").upper()
        if fmt not in ALLOWED_FORMATS:
            raise ImageValidationError(f"Unsupported format: {fmt}. Allowed: {', '.join(ALLOWED_FORMATS)}")

    @staticmethod
    def _validate_dimensions(img: Image.Image) -> None:
        if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
            raise ImageValidationError(
                f"Image too large ({img.width}x{img.height}), limit {MAX_WIDTH}x{MAX_HEIGHT}"
            )

    @staticmethod
    def _strip_exif_and_normalize(img: Image.Image, fmt: str) -> BytesIO:
        """Removes EXIF metadata and ensures consistent encoding."""
        if fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            img = background

        out = BytesIO()
        img.save(out, format=fmt, **({"quality": 90, "optimize": True} if fmt == "JPEG" else {"optimize": True}))
        out.seek(0)
        return out

    @staticmethod
    def _process_image_sync(file_bytes: bytes, content_type: str) -> Tuple[BytesIO, str]:
        """Validates and normalizes image synchronously (run in threadpool)."""
        if content_type not in ALLOWED_MIME:
            raise ImageValidationError(f"Unsupported MIME type: {content_type}")

        ImageProcessor._ensure_size_limit(file_bytes)
        img = ImageProcessor._open_and_verify(file_bytes)
        ImageProcessor._validate_format(img)
        ImageProcessor._validate_dimensions(img)

        fmt = (img.format or "JPEG").upper()
        ext = EXT_BY_FORMAT.get(fmt, "jpg")
        processed = ImageProcessor._strip_exif_and_normalize(img, fmt)

        logger.info("image_validated", format=fmt, size=len(file_bytes), dimensions=f"{img.width}x{img.height}")
        return processed, ext

    # -----------------------------
    # DeepAI NSFW Check
    # -----------------------------
    @staticmethod
    async def detect_nsfw(image_url: str) -> Optional[Dict]:
        if not DEEPAI_API_KEY:
            logger.error("deepai_key_missing")
            raise HTTPException(status_code=500, detail="DeepAI API key not configured")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(
                    "https://api.deepai.org/api/nsfw-detector",
                    headers={"api-key": DEEPAI_API_KEY},
                    data={"image": image_url},
                ) as resp:
                    if resp.status != 200:
                        msg = await resp.text()
                        logger.error("deepai_failed", status=resp.status, msg=msg)
                        return {"error": f"DeepAI returned {resp.status}: {msg}"}

                    data = await resp.json()
                    nsfw_score = data.get("output", {}).get("nsfw_score", 0)
                    result = {
                        "is_nsfw": nsfw_score > 0.5,
                        "confidence": nsfw_score * 100,
                        "raw": data,
                    }
                    logger.info("deepai_check_done", nsfw_score=nsfw_score)
                    return result
        except Exception as e:
            logger.error("deepai_exception", error=str(e), exc_info=True)
            return {"error": str(e)}

    # -----------------------------
    # Main entrypoint
    # -----------------------------
    @staticmethod
    async def process_and_save(
        file: UploadFile,
        upload_dir: Path,
        public_base_url: str,
        company_uuid: Optional[str] = None,
        check_nsfw: bool = True,
    ) -> Dict:
        """Validates, sanitizes, saves the image, and optionally runs NSFW detection."""
        try:
            file_bytes = await file.read()
            processed_io, ext = await run_in_threadpool(
                ImageProcessor._process_image_sync, file_bytes, file.content_type or "image/jpeg"
            )

            filename = f"{company_uuid or uuid.uuid4()}.{ext}"
            save_path = upload_dir / filename
            tmp_path = save_path.with_suffix(f".{uuid.uuid4().hex}.tmp")

            await run_in_threadpool(tmp_path.write_bytes, processed_io.read())
            await run_in_threadpool(os.replace, str(tmp_path), str(save_path))
            logger.info("image_saved", path=str(save_path))

            image_url = f"{public_base_url.rstrip('/')}/{filename}"

            result: Dict = {
                "filename": filename,
                "path": str(save_path),
                "url": image_url,
                "size": save_path.stat().st_size,
            }

            if check_nsfw and settings.enable_content_moderation:
                nsfw_result = await ImageProcessor.detect_nsfw(image_url)
                if nsfw_result:
                    result["nsfw_check"] = nsfw_result
                    if nsfw_result.get("is_nsfw"):
                        result["nsfw_flagged"] = True
                        logger.warning("nsfw_flagged", filename=filename, confidence=nsfw_result["confidence"])

            return result

        except ImageValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            logger.error("image_processing_failed", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to process image")


image_processor = ImageProcessor()
