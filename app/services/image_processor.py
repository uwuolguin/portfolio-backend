import os
import uuid
from io import BytesIO
from typing import Dict, Optional, Tuple
from pathlib import Path
from enum import Enum

import aiohttp
from PIL import Image, UnidentifiedImageError
from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_SIZE_BYTES = settings.max_file_size
MAX_WIDTH = 4000
MAX_HEIGHT = 4000
ALLOWED_FORMATS = {"JPEG", "PNG"}
ALLOWED_MIME = set(settings.allowed_file_types)
EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png"}


class NSFWProvider(str, Enum):
    """Available free NSFW detection providers"""
    NSFW_CATEGORIZE = "nsfw_categorize"
    DEEPAI = "deepai"
    SIGHTENGINE = "sightengine"
    DISABLED = "disabled"


# NSFW provider configuration
NSFW_PROVIDER = os.getenv("NSFW_PROVIDER", NSFWProvider.DISABLED.value)
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY")
SIGHTENGINE_USER = os.getenv("SIGHTENGINE_USER")
SIGHTENGINE_SECRET = os.getenv("SIGHTENGINE_SECRET")


class ImageValidationError(ValueError):
    """Custom exception for image validation failures."""
    pass


# ---------------------------------------------------------------------------
# Image Processor
# ---------------------------------------------------------------------------

class ImageProcessor:
    """Async image processor for security and optimization."""

    # -----------------------------
    # Image Validation & Conversion
    # -----------------------------
    @staticmethod
    def _ensure_size_limit(file_bytes: bytes) -> None:
        if len(file_bytes) > MAX_SIZE_BYTES:
            size_mb = len(file_bytes) / (1024 * 1024)
            limit_mb = MAX_SIZE_BYTES / (1024 * 1024)
            raise ImageValidationError(
                f"Image too large: {size_mb:.2f}MB (limit: {limit_mb:.2f}MB)"
            )

    @staticmethod
    def _open_and_verify(file_bytes: bytes) -> Image.Image:
        try:
            with Image.open(BytesIO(file_bytes)) as img:
                img.load()  # ensures image integrity
                return img.copy()
        except (UnidentifiedImageError, Exception) as e:
            raise ImageValidationError("Not a valid image file") from e

    @staticmethod
    def _validate_dimensions(img: Image.Image) -> None:
        if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
            raise ImageValidationError(
                f"Image dimensions too large: {img.width}x{img.height}px "
                f"(max: {MAX_WIDTH}x{MAX_HEIGHT}px)"
            )

    @staticmethod
    def _validate_format(img: Image.Image) -> None:
        fmt = (img.format or "").upper()
        if fmt not in ALLOWED_FORMATS:
            raise ImageValidationError(
                f"Unsupported format: {fmt}. Allowed: {', '.join(ALLOWED_FORMATS)}"
            )

    @staticmethod
    def _strip_exif_and_normalize(img: Image.Image, target_format: str) -> BytesIO:
        """Remove EXIF data, normalize and optimize image."""
        if target_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            img = background

        out = BytesIO()
        save_kwargs = {
            "JPEG": {"quality": 90, "optimize": True, "progressive": True},
            "PNG": {"optimize": True},
        }.get(target_format, {})

        img.save(out, format=target_format, **save_kwargs)
        out.seek(0)
        return out

    @staticmethod
    def _process_image_sync(file_bytes: bytes, content_type: str) -> Tuple[BytesIO, str]:
        if content_type not in ALLOWED_MIME:
            raise ImageValidationError(f"Unsupported content type: {content_type}")

        ImageProcessor._ensure_size_limit(file_bytes)
        img = ImageProcessor._open_and_verify(file_bytes)
        ImageProcessor._validate_format(img)
        ImageProcessor._validate_dimensions(img)

        fmt = (img.format or "JPEG").upper()
        ext = EXT_BY_FORMAT.get(fmt, "jpg")

        processed_io = ImageProcessor._strip_exif_and_normalize(img, fmt)

        logger.info(
            "image_processed",
            original_size=len(file_bytes),
            processed_size=len(processed_io.getvalue()),
            format=fmt,
            dimensions=f"{img.width}x{img.height}",
        )

        return processed_io, ext

    # -----------------------------
    # NSFW Providers
    # -----------------------------

    @staticmethod
    async def _check_nsfw_categorize(image_url: str) -> Dict:
        """FREE: 10/day per IP."""
        try:
            url = "https://nsfw-categorize.it/api/upload"
            params = {"url": image_url}

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return {"error": f"API returned {resp.status}"}
                    result = await resp.json()

                    if result.get("status") == "OK":
                        data = result["data"]
                        is_nsfw = data.get("nsfw", False) or data.get("porn", False)
                        return {
                            "provider": "nsfw_categorize",
                            "is_nsfw": is_nsfw,
                            "confidence": data.get("confidence", 0),
                            "classification": data.get("classification"),
                            "details": data,
                        }

                    return {"error": result.get("reason", "Unknown error")}

        except Exception as e:
            logger.error("nsfw_categorize_error", error=str(e), exc_info=True)
            return {"error": str(e)}

    @staticmethod
    async def _check_deepai(image_url: str) -> Dict:
        """FREE: 500 calls/month."""
        if not DEEPAI_API_KEY:
            return {"error": "DEEPAI_API_KEY not configured"}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(
                    "https://api.deepai.org/api/nsfw-detector",
                    headers={"api-key": DEEPAI_API_KEY},
                    data={"image": image_url},
                ) as resp:
                    if resp.status != 200:
                        return {"error": f"API returned {resp.status}"}

                    result = await resp.json()
                    nsfw_score = result.get("output", {}).get("nsfw_score", 0)
                    is_nsfw = nsfw_score > 0.5
                    return {
                        "provider": "deepai",
                        "is_nsfw": is_nsfw,
                        "confidence": nsfw_score * 100,
                        "details": result.get("output", {}),
                    }

        except Exception as e:
            logger.error("deepai_error", error=str(e), exc_info=True)
            return {"error": str(e)}

    @staticmethod
    async def _check_sightengine(image_url: str) -> Dict:
        """FREE: 2000/month."""
        if not (SIGHTENGINE_USER and SIGHTENGINE_SECRET):
            return {"error": "SIGHTENGINE credentials not configured"}

        try:
            params = {
                "url": image_url,
                "models": "nudity-2.0",
                "api_user": SIGHTENGINE_USER,
                "api_secret": SIGHTENGINE_SECRET,
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get("https://api.sightengine.com/1.0/check.json", params=params) as resp:
                    if resp.status != 200:
                        return {"error": f"API returned {resp.status}"}
                    result = await resp.json()

                    if result.get("status") != "success":
                        return {"error": result.get("error", {}).get("message", "Unknown error")}

                    nudity = result.get("nudity", {})
                    raw_score, partial_score = nudity.get("raw", 0), nudity.get("partial", 0)
                    is_nsfw = raw_score > 0.5 or partial_score > 0.5
                    return {
                        "provider": "sightengine",
                        "is_nsfw": is_nsfw,
                        "confidence": max(raw_score, partial_score) * 100,
                        "details": nudity,
                    }

        except Exception as e:
            logger.error("sightengine_error", error=str(e), exc_info=True)
            return {"error": str(e)}

    # -----------------------------
    # NSFW Router
    # -----------------------------

    @staticmethod
    async def detect_nsfw(image_url: str) -> Optional[Dict]:
        if not settings.enable_content_moderation or NSFW_PROVIDER == NSFWProvider.DISABLED.value:
            return None

        providers = {
            NSFWProvider.NSFW_CATEGORIZE.value: ImageProcessor._check_nsfw_categorize,
            NSFWProvider.DEEPAI.value: ImageProcessor._check_deepai,
            NSFWProvider.SIGHTENGINE.value: ImageProcessor._check_sightengine,
        }

        handler = providers.get(NSFW_PROVIDER)
        if not handler:
            return {"error": f"Unknown provider: {NSFW_PROVIDER}"}
        return await handler(image_url)

    # -----------------------------
    # Main entry point
    # -----------------------------

    @staticmethod
    async def process_and_save(
        file: UploadFile,
        upload_dir: Path,
        company_uuid: Optional[str] = None,
        check_nsfw: bool = False,
        public_base_url: Optional[str] = None,
    ) -> Dict[str, any]:
        try:
            file_bytes = await file.read()
            content_type = file.content_type or "image/jpeg"

            processed_io, ext = await run_in_threadpool(
                ImageProcessor._process_image_sync, file_bytes, content_type
            )

            filename = f"{company_uuid or uuid.uuid4()}.{ext}"
            save_path = upload_dir / filename
            tmp_path = save_path.with_suffix(f".{uuid.uuid4().hex}.tmp")

            await run_in_threadpool(tmp_path.write_bytes, processed_io.read())
            await run_in_threadpool(os.replace, str(tmp_path), str(save_path))

            logger.info("image_saved", filename=filename, path=str(save_path))

            result: Dict[str, any] = {
                "filename": filename,
                "path": str(save_path),
                "size": save_path.stat().st_size,
            }

            if check_nsfw and public_base_url:
                image_url = f"{public_base_url.rstrip('/')}/{filename}"
                nsfw_result = await ImageProcessor.detect_nsfw(image_url)
                if nsfw_result:
                    result["nsfw_check"] = nsfw_result
                    if nsfw_result.get("is_nsfw"):
                        result["nsfw_flagged"] = True
                        logger.warning(
                            "nsfw_content_detected",
                            filename=filename,
                            provider=nsfw_result.get("provider"),
                            confidence=nsfw_result.get("confidence"),
                        )

            return result

        except ImageValidationError as e:
            logger.warning("image_validation_failed", error=str(e))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        except Exception as e:
            logger.error("image_processing_failed", error=str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process image",
            )


image_processor = ImageProcessor()
