import uuid
import structlog
from pathlib import Path
from typing import Optional
from io import BytesIO

from fastapi import UploadFile, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from opennsfw2 import make_open_nsfw_model, predict_image

from app.config import settings

logger = structlog.get_logger(__name__)


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

    @staticmethod
    def load_nsfw_model() -> None:
        """Initialize NSFW model once at startup."""
        if FileHandler._nsfw_model is None:
            logger.info("nsfw_model_loading")
            FileHandler._nsfw_model = make_open_nsfw_model()
            logger.info("nsfw_model_loaded")

    @staticmethod
    def init_upload_directory() -> None:
        """Ensure upload directory exists."""
        FileHandler.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("upload_directory_initialized", path=str(FileHandler.UPLOAD_DIR))

    @staticmethod
    def _validate_and_process_image(file_bytes: bytes, content_type: str) -> tuple[BytesIO, str]:
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
    def _check_nsfw_sync(image_bytes: bytes) -> float:
        """Run NSFW detection in threadpool. Returns float score 0.0–1.0."""
        try:
            img_stream = BytesIO(image_bytes)
            score = predict_image(img_stream, model=FileHandler._nsfw_model)
            return float(score)
        except Exception as e:
            logger.error("nsfw_check_failed", error=str(e))
            return 0.0

    @staticmethod
    async def save_image(
        file: UploadFile,
        company_uuid: Optional[str] = None,
        **kwargs
    ) -> str:
        try:
            file_bytes = await file.read()

            processed_io, ext = await run_in_threadpool(
                FileHandler._validate_and_process_image,
                file_bytes,
                file.content_type or "image/jpeg"
            )

            nsfw_score = await run_in_threadpool(FileHandler._check_nsfw_sync, file_bytes)
            if nsfw_score > 0.98:
                logger.warning("nsfw_image_rejected", nsfw_score=nsfw_score)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image rejected for inappropriate content"
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
                size=save_path.stat().st_size
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
        filename = Path(image_path).name
        return f"{request_base_url.rstrip('/')}/uploads/{filename}"
