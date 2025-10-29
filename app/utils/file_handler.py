import uuid
import structlog
from pathlib import Path
from typing import Optional
from io import BytesIO

from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError

from app.config import settings

logger = structlog.get_logger(__name__)


class NSFWModelError(Exception):
    """Custom exception for NSFW model issues"""
    pass


class FileHandler:
    """
    Handles image upload, validation, and deletion.
    Includes NSFW detection using OpenNSFW2.
    """

    UPLOAD_DIR = Path("uploads/company_images")
    MAX_SIZE_BYTES = settings.max_file_size
    MAX_WIDTH = 4000
    MAX_HEIGHT = 4000
    ALLOWED_FORMATS = {"JPEG", "PNG"}
    ALLOWED_MIME = set(settings.allowed_file_types)
    EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png"}

    _nsfw_model = None
    _nsfw_available = False
    
    NSFW_THRESHOLD = 0.75  

    @staticmethod
    def load_nsfw_model() -> None:
        """
        Initialize NSFW model once at startup.
        Forces weight download if needed.
        
        NOTE: opennsfw2 v0.14+ handles model internally, no need to pass it
        """
        if FileHandler._nsfw_available:
            logger.info("nsfw_model_already_loaded")
            return

        try:
            logger.info("nsfw_model_loading_starting")
            
            from opennsfw2 import predict_image
            
            logger.info("nsfw_model_building", message="This may download weights (~40MB) on first run")
            
            logger.info("nsfw_model_testing")
            test_img = Image.new('RGB', (224, 224), color='red')
            test_bytes = BytesIO()
            test_img.save(test_bytes, format='JPEG')
            test_bytes.seek(0)
            
            test_score = predict_image(test_bytes)
            
            logger.info(
                "nsfw_model_loaded_successfully",
                test_score=float(test_score),
                message=f"Model operational (test score: {test_score:.4f})"
            )
            
            FileHandler._nsfw_model = True
            FileHandler._nsfw_available = True
            
        except ImportError as e:
            logger.error(
                "nsfw_model_import_failed",
                error=str(e),
                message="Install with: pip install opennsfw2"
            )
            FileHandler._nsfw_available = False
            
        except Exception as e:
            logger.error(
                "nsfw_model_load_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            FileHandler._nsfw_available = False
            
            if "urlopen" in str(e) or "URLError" in str(e) or "Connection" in str(e):
                logger.critical(
                    "nsfw_model_download_failed",
                    message="Cannot download model weights. Check internet connection."
                )

    @staticmethod
    def init_upload_directory() -> None:
        """Ensure upload directory exists."""
        FileHandler.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("upload_directory_initialized", path=str(FileHandler.UPLOAD_DIR))

    @staticmethod
    def _validate_and_process_image(
        file_bytes: bytes, 
        content_type: str
    ) -> tuple[BytesIO, str]:
        """Validate and process image synchronously."""
        
        if content_type not in FileHandler.ALLOWED_MIME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported MIME type: {content_type}"
            )

        if len(file_bytes) > FileHandler.MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image too large ({len(file_bytes)/1_048_576:.2f} MB), "
                       f"limit {FileHandler.MAX_SIZE_BYTES/1_048_576:.2f} MB"
            )

        try:
            with Image.open(BytesIO(file_bytes)) as img:
                img.load()
                fmt = (img.format or "").upper() 
                img_copy = img.copy()
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or corrupted image file"
            )

        if fmt not in FileHandler.ALLOWED_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format: {fmt}. Allowed: {', '.join(FileHandler.ALLOWED_FORMATS)}"
            )

        if img_copy.width > FileHandler.MAX_WIDTH or img_copy.height > FileHandler.MAX_HEIGHT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image too large ({img_copy.width}x{img_copy.height}), "
                       f"limit {FileHandler.MAX_WIDTH}x{FileHandler.MAX_HEIGHT}"
            )

        if img_copy.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img_copy.size, (255, 255, 255))
            if img_copy.mode == "P":
                img_copy = img_copy.convert("RGBA")
            background.paste(img_copy, mask=img_copy.split()[-1])
            img_copy = background

        out = BytesIO()
        save_params = {"quality": 90, "optimize": True} if fmt == "JPEG" else {"optimize": True}
        img_copy.save(out, format=fmt, **save_params)
        out.seek(0)

        ext = FileHandler.EXT_BY_FORMAT.get(fmt, "jpg")

        logger.info(
            "image_validated",
            format=fmt,
            size=len(file_bytes),
            dimensions=f"{img_copy.width}x{img_copy.height}"
        )

        return out, ext

    @staticmethod
    def _check_nsfw_sync(image_bytes: bytes) -> tuple[float, bool]:
        """
        Run NSFW detection in threadpool.
        Returns (score, check_performed)
        
        IMPORTANT: If model unavailable, returns (1.0, False) to REJECT by default
        This is safer - requires manual review if NSFW check can't run
        """
        if not FileHandler._nsfw_available:
            logger.warning(
                "nsfw_check_unavailable_blocking_upload",
                message="NSFW model not loaded - blocking upload for safety"
            )
            return (1.0, False)

        try:
            from opennsfw2 import predict_image
            
            img_stream = BytesIO(image_bytes)
            score = predict_image(img_stream)
            
            logger.info(
                "nsfw_check_completed",
                score=float(score),
                threshold=FileHandler.NSFW_THRESHOLD,
                will_block=score > FileHandler.NSFW_THRESHOLD
            )
            
            return (float(score), True)
            
        except Exception as e:
            logger.error(
                "nsfw_check_execution_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return (1.0, False)

    @staticmethod
    async def save_image(
        file: UploadFile,
        company_uuid: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Save and validate uploaded image with NSFW checking.
        Returns the file path as string.
        """
        try:
            file_bytes = await file.read()

            processed_io, ext = await run_in_threadpool(
                FileHandler._validate_and_process_image,
                file_bytes,
                file.content_type or "image/jpeg"
            )

            nsfw_score, check_performed = await run_in_threadpool(
                FileHandler._check_nsfw_sync, 
                file_bytes
            )

            if nsfw_score > FileHandler.NSFW_THRESHOLD:
                if check_performed:
                    logger.warning(
                        "nsfw_image_rejected",
                        nsfw_score=nsfw_score,
                        threshold=FileHandler.NSFW_THRESHOLD,
                        company_uuid=company_uuid,
                        reason="explicit_content_detected"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Image rejected: inappropriate content detected (confidence: {nsfw_score:.1%})"
                    )
                else:
                    logger.error(
                        "nsfw_check_failed_blocking_upload",
                        company_uuid=company_uuid,
                        reason="nsfw_model_unavailable"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Content moderation service unavailable. Please try again later."
                    )
            
            if check_performed:
                logger.info(
                    "nsfw_check_passed",
                    score=nsfw_score,
                    threshold=FileHandler.NSFW_THRESHOLD
                )
            else:
                logger.warning(
                    "image_uploaded_without_nsfw_check",
                    company_uuid=company_uuid,
                    score=nsfw_score
                )

            filename = f"{company_uuid or uuid.uuid4()}.{ext}"
            save_path = FileHandler.UPLOAD_DIR / filename
            tmp_path = save_path.with_suffix(f".{uuid.uuid4().hex}.tmp")

            def _atomic_save():
                tmp_path.write_bytes(processed_io.getvalue())
                tmp_path.replace(save_path)

            await run_in_threadpool(_atomic_save)

            logger.info(
                "image_saved_successfully",
                filename=filename,
                path=str(save_path),
                size=save_path.stat().st_size,
                nsfw_checked=check_performed,
                nsfw_score=nsfw_score
            )

            return str(save_path)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("file_save_error", error=str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save image"
            )

    @staticmethod
    def delete_image(image_path: str) -> bool:
        """Delete an image file. Returns True if successful."""
        try:
            file_path = Path(image_path)
            if file_path.exists():
                file_path.unlink()
                logger.info("file_deleted", path=image_path)
                return True
            logger.warning("file_not_found_for_deletion", path=image_path)
            return False
        except Exception as e:
            logger.error("file_delete_error", path=image_path, error=str(e))
            return False

    @staticmethod
    def get_image_url(image_path: str, request_base_url: str) -> str:
        """Convert file path to public URL."""
        filename = Path(image_path).name
        return f"{request_base_url.rstrip('/')}/uploads/{filename}"

    @staticmethod
    def get_nsfw_status() -> dict:
        """Get current NSFW checking status (useful for admin dashboard)."""
        return {
            "available": FileHandler._nsfw_available,
            "model_loaded": FileHandler._nsfw_available,  
            "status": "active" if FileHandler._nsfw_available else "disabled",
            "threshold": FileHandler.NSFW_THRESHOLD
        }