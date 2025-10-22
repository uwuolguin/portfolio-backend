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

MAX_SIZE_BYTES = settings.max_file_size
MAX_WIDTH = 4000
MAX_HEIGHT = 4000
ALLOWED_FORMATS = {"JPEG", "PNG"}
ALLOWED_MIME = set(settings.allowed_file_types)
EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png"}


class NSFWProvider(str, Enum):
    """Available FREE NSFW detection providers"""
    NSFW_CATEGORIZE = "nsfw_categorize"  # 10 free/day per IP
    DEEPAI = "deepai"  # Free tier available
    SIGHTENGINE = "sightengine"  # 2000 free/month
    DISABLED = "disabled"


# NSFW API Configuration
NSFW_PROVIDER = os.getenv("NSFW_PROVIDER", NSFWProvider.DISABLED.value)

# Provider-specific API keys (optional for some)
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY")  # Get free at https://deepai.org
SIGHTENGINE_USER = os.getenv("SIGHTENGINE_USER")  # Get free at https://sightengine.com
SIGHTENGINE_SECRET = os.getenv("SIGHTENGINE_SECRET")


class ImageValidationError(ValueError):
    """Custom exception for image validation failures"""
    pass


class ImageProcessor:
    """Async image processor for security and optimization"""
    
    @staticmethod
    def _ensure_size_limit(file_bytes: bytes) -> None:
        """Check file size limit"""
        if len(file_bytes) > MAX_SIZE_BYTES:
            size_mb = len(file_bytes) / (1024 * 1024)
            limit_mb = MAX_SIZE_BYTES / (1024 * 1024)
            raise ImageValidationError(
                f"Image too large: {size_mb:.2f}MB (limit: {limit_mb:.2f}MB)"
            )
    
    @staticmethod
    def _open_and_verify(file_bytes: bytes) -> Image.Image:
        """Open image and verify it's valid"""
        bio = BytesIO(file_bytes)
        try:
            img = Image.open(bio)
            img.verify()
        except (UnidentifiedImageError, Exception) as e:
            raise ImageValidationError("Not a valid image file") from e
        
        bio.seek(0)
        return Image.open(bio)
    
    @staticmethod
    def _validate_dimensions(img: Image.Image) -> None:
        """Check image dimensions"""
        if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
            raise ImageValidationError(
                f"Image dimensions too large: {img.width}x{img.height}px "
                f"(max: {MAX_WIDTH}x{MAX_HEIGHT}px)"
            )
    
    @staticmethod
    def _validate_format(img: Image.Image) -> None:
        """Check image format"""
        fmt = (img.format or "").upper()
        if fmt not in ALLOWED_FORMATS:
            raise ImageValidationError(
                f"Unsupported format: {fmt}. Allowed: {', '.join(ALLOWED_FORMATS)}"
            )
    
    @staticmethod
    def _strip_exif_and_normalize(img: Image.Image, target_format: str) -> BytesIO:
        """
        Remove EXIF metadata and normalize image
        - Strips potentially malicious EXIF data
        - Converts to standard format
        - Optimizes file size
        """
        if target_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
        
        out = BytesIO()
        save_kwargs = {}
        
        if target_format == "JPEG":
            save_kwargs.update({
                "quality": 90,
                "optimize": True,
                "progressive": True
            })
        elif target_format == "PNG":
            save_kwargs.update({"optimize": True})
        
        img.save(out, format=target_format, **save_kwargs)
        out.seek(0)
        return out
    
    @staticmethod
    def _process_image_sync(file_bytes: bytes, content_type: str) -> Tuple[BytesIO, str]:
        """
        Synchronous CPU-intensive image processing
        Called via run_in_threadpool to avoid blocking
        """
        if content_type not in ALLOWED_MIME:
            raise ImageValidationError(f"Unsupported content type: {content_type}")
        
        ImageProcessor._ensure_size_limit(file_bytes)
        img = ImageProcessor._open_and_verify(file_bytes)
        ImageProcessor._validate_format(img)
        ImageProcessor._validate_dimensions(img)
        
        fmt = (img.format or "").upper()
        fmt = fmt if fmt in ALLOWED_FORMATS else "JPEG"
        ext = EXT_BY_FORMAT.get(fmt, "jpg")
        
        processed_io = ImageProcessor._strip_exif_and_normalize(img, fmt)
        
        logger.info(
            "image_processed",
            original_size=len(file_bytes),
            processed_size=len(processed_io.getvalue()),
            format=fmt,
            dimensions=f"{img.width}x{img.height}"
        )
        
        return processed_io, ext
    
    @staticmethod
    async def _check_nsfw_categorize(image_url: str) -> Optional[Dict]:
        """
        FREE: 10 requests/day per IP
        Website: https://nsfw-categorize.it/
        No API key needed!
        """
        try:
            url = "https://nsfw-categorize.it/api/upload"
            params = {"url": image_url}
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning("nsfw_categorize_error", status=resp.status)
                        return {"error": f"API returned {resp.status}"}
                    
                    result = await resp.json()
                    
                    if result.get("status") == "OK":
                        data = result.get("data", {})
                        is_nsfw = data.get("nsfw", False) or data.get("porn", False)
                        
                        logger.info(
                            "nsfw_categorize_check_completed",
                            classification=data.get("classification"),
                            confidence=data.get("confidence"),
                            nsfw=is_nsfw
                        )
                        
                        return {
                            "provider": "nsfw_categorize",
                            "is_nsfw": is_nsfw,
                            "confidence": data.get("confidence", 0),
                            "classification": data.get("classification"),
                            "details": data
                        }
                    elif result.get("status") == "NOQUOTA":
                        logger.warning("nsfw_categorize_quota_exceeded")
                        return {"error": "Daily quota exceeded (10/day per IP)"}
                    else:
                        return {"error": result.get("reason", "Unknown error")}
                        
        except Exception as e:
            logger.error("nsfw_categorize_error", error=str(e), exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    async def _check_deepai(image_url: str) -> Optional[Dict]:
        """
        FREE: 500 calls/month with free API key
        Website: https://deepai.org (signup for free key)
        """
        if not DEEPAI_API_KEY:
            logger.debug("deepai_skipped", reason="no_api_key")
            return {"error": "DEEPAI_API_KEY not configured"}
        
        try:
            url = "https://api.deepai.org/api/nsfw-detector"
            headers = {"api-key": DEEPAI_API_KEY}
            data = {"image": image_url}
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, data=data) as resp:
                    if resp.status != 200:
                        logger.warning("deepai_error", status=resp.status)
                        return {"error": f"API returned {resp.status}"}
                    
                    result = await resp.json()
                    
                    # DeepAI returns a score between 0-1 (0=safe, 1=nsfw)
                    nsfw_score = result.get("output", {}).get("nsfw_score", 0)
                    is_nsfw = nsfw_score > 0.5  # Threshold
                    
                    logger.info(
                        "deepai_check_completed",
                        nsfw_score=nsfw_score,
                        is_nsfw=is_nsfw
                    )
                    
                    return {
                        "provider": "deepai",
                        "is_nsfw": is_nsfw,
                        "confidence": nsfw_score * 100,
                        "nsfw_score": nsfw_score,
                        "details": result.get("output", {})
                    }
                        
        except Exception as e:
            logger.error("deepai_error", error=str(e), exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    async def _check_sightengine(image_url: str) -> Optional[Dict]:
        """
        FREE: 2000 operations/month
        Website: https://sightengine.com (signup for free credits)
        """
        if not SIGHTENGINE_USER or not SIGHTENGINE_SECRET:
            logger.debug("sightengine_skipped", reason="credentials_not_configured")
            return {"error": "SIGHTENGINE credentials not configured"}
        
        try:
            url = "https://api.sightengine.com/1.0/check.json"
            params = {
                "url": image_url,
                "models": "nudity-2.0",
                "api_user": SIGHTENGINE_USER,
                "api_secret": SIGHTENGINE_SECRET
            }
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning("sightengine_error", status=resp.status)
                        return {"error": f"API returned {resp.status}"}
                    
                    result = await resp.json()
                    
                    if result.get("status") == "success":
                        nudity = result.get("nudity", {})
                        
                        # Check various nudity classifications
                        raw_score = nudity.get("raw", 0)
                        partial_score = nudity.get("partial", 0)
                        safe_score = nudity.get("safe", 0)
                        
                        # Flag if raw or partial nudity score is high
                        is_nsfw = raw_score > 0.5 or partial_score > 0.5
                        
                        logger.info(
                            "sightengine_check_completed",
                            raw=raw_score,
                            partial=partial_score,
                            safe=safe_score,
                            is_nsfw=is_nsfw
                        )
                        
                        return {
                            "provider": "sightengine",
                            "is_nsfw": is_nsfw,
                            "confidence": max(raw_score, partial_score) * 100,
                            "raw_nudity": raw_score,
                            "partial_nudity": partial_score,
                            "safe": safe_score,
                            "details": nudity
                        }
                    else:
                        return {"error": result.get("error", {}).get("message", "Unknown error")}
                        
        except Exception as e:
            logger.error("sightengine_error", error=str(e), exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    async def detect_nsfw(image_url: str) -> Optional[Dict]:
        """
        Check for NSFW content using configured provider
        Returns None if disabled or check fails
        """
        if not settings.enable_content_moderation:
            logger.debug("nsfw_check_skipped", reason="moderation_disabled")
            return None
        
        if NSFW_PROVIDER == NSFWProvider.DISABLED.value:
            logger.debug("nsfw_check_skipped", reason="provider_disabled")
            return None
        
        # Route to appropriate provider
        if NSFW_PROVIDER == NSFWProvider.NSFW_CATEGORIZE.value:
            return await ImageProcessor._check_nsfw_categorize(image_url)
        elif NSFW_PROVIDER == NSFWProvider.DEEPAI.value:
            return await ImageProcessor._check_deepai(image_url)
        elif NSFW_PROVIDER == NSFWProvider.SIGHTENGINE.value:
            return await ImageProcessor._check_sightengine(image_url)
        else:
            logger.warning("unknown_nsfw_provider", provider=NSFW_PROVIDER)
            return {"error": f"Unknown provider: {NSFW_PROVIDER}"}
    
    @staticmethod
    async def process_and_save(
        file: UploadFile,
        upload_dir: Path,
        company_uuid: Optional[str] = None,
        check_nsfw: bool = False,
        public_base_url: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Main async entry point for image processing
        
        Args:
            file: Uploaded file
            upload_dir: Directory to save processed image
            company_uuid: Optional UUID for filename
            check_nsfw: Whether to check for NSFW content
            public_base_url: Base URL for NSFW check
            
        Returns:
            Dict with filename, path, and optional NSFW results
        """
        try:
            # Read file content
            file_bytes = await file.read()
            content_type = file.content_type or "image/jpeg"
            
            # Process image in thread pool (CPU-intensive)
            processed_io, ext = await run_in_threadpool(
                ImageProcessor._process_image_sync,
                file_bytes,
                content_type
            )
            
            # Generate filename
            filename = f"{company_uuid or uuid.uuid4()}.{ext}"
            save_path = upload_dir / filename
            
            # Save atomically with temp file
            tmp_path = save_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            
            # Write in thread pool
            await run_in_threadpool(tmp_path.write_bytes, processed_io.read())
            
            # Atomic rename
            await run_in_threadpool(os.replace, str(tmp_path), str(save_path))
            
            logger.info("image_saved", filename=filename, path=str(save_path))
            
            result = {
                "filename": filename,
                "path": str(save_path),
                "size": save_path.stat().st_size
            }
            
            # Optional NSFW check
            if check_nsfw and public_base_url:
                # Construct public URL for the saved image
                image_url = f"{public_base_url.rstrip('/')}/{save_path}"
                nsfw_result = await ImageProcessor.detect_nsfw(image_url)
                
                if nsfw_result and not nsfw_result.get("error"):
                    result["nsfw_check"] = nsfw_result
                    
                    # Check if flagged as NSFW
                    if nsfw_result.get("is_nsfw"):
                        logger.warning(
                            "nsfw_content_detected",
                            filename=filename,
                            provider=nsfw_result.get("provider"),
                            confidence=nsfw_result.get("confidence")
                        )
                        result["nsfw_flagged"] = True
                elif nsfw_result and nsfw_result.get("error"):
                    # Log error but don't block upload
                    logger.warning(
                        "nsfw_check_failed_allowing_upload",
                        error=nsfw_result.get("error")
                    )
            
            return result
            
        except ImageValidationError as e:
            logger.warning("image_validation_failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except Exception as e:
            logger.error("image_processing_failed", error=str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process image"
            )



image_processor = ImageProcessor()