import uuid
import structlog
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from fastapi.concurrency import run_in_threadpool

from app.config import settings

logger = structlog.get_logger(__name__)


class FileHandler:
    UPLOAD_DIR = Path("uploads/company_images")
    MAX_SIZE_BYTES = settings.max_file_size
    MAX_WIDTH = 4000
    MAX_HEIGHT = 4000
    ALLOWED_FORMATS = {"JPEG", "PNG"}
    ALLOWED_MIME = set(settings.allowed_file_types)
    EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png"}

    @staticmethod
    def init_upload_directory() -> None:
        """Ensure upload directory exists."""
        FileHandler.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("upload_directory_initialized", path=str(FileHandler.UPLOAD_DIR))

    @staticmethod
    def _validate_and_process_image(file_bytes: bytes, content_type: str) -> tuple[BytesIO, str]:
        """Validate and process image synchronously."""
        # Check MIME type
        if content_type not in FileHandler.ALLOWED_MIME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported MIME type: {content_type}"
            )

        # Check file size
        if len(file_bytes) > FileHandler.MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image too large ({len(file_bytes)/1_048_576:.2f} MB), "
                       f"limit {FileHandler.MAX_SIZE_BYTES/1_048_576:.2f} MB"
            )

        # Open and verify image
        try:
            with Image.open(BytesIO(file_bytes)) as img:
                img.load()
                img_copy = img.copy()
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format or corrupted image"
            )

        # Validate format
        fmt = (img_copy.format or "").upper()
        if fmt not in FileHandler.ALLOWED_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format: {fmt}. Allowed: {', '.join(FileHandler.ALLOWED_FORMATS)}"
            )

        # Validate dimensions
        if img_copy.width > FileHandler.MAX_WIDTH or img_copy.height > FileHandler.MAX_HEIGHT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image too large ({img_copy.width}x{img_copy.height}), "
                       f"limit {FileHandler.MAX_WIDTH}x{FileHandler.MAX_HEIGHT}"
            )

        # Strip EXIF and normalize
        if fmt == "JPEG" and img_copy.mode in ("RGBA", "P", "LA"):
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
    async def save_image(
        file: UploadFile,
        company_uuid: Optional[str] = None,
        **kwargs  # Accept but ignore legacy parameters
    ) -> str:
        """
        Save and process an uploaded image with validation.

        Args:
            file: Uploaded file.
            company_uuid: Optional UUID for filename.

        Returns:
            str: Relative path to the saved image (e.g., "uploads/company_images/uuid.jpg")

        Raises:
            HTTPException: If validation fails.
        """
        try:
            # Read file
            file_bytes = await file.read()
            
            # Validate and process in thread pool
            processed_io, ext = await run_in_threadpool(
                FileHandler._validate_and_process_image,
                file_bytes,
                file.content_type or "image/jpeg"
            )

            # Generate filename
            filename = f"{company_uuid or uuid.uuid4()}.{ext}"
            save_path = FileHandler.UPLOAD_DIR / filename
            tmp_path = save_path.with_suffix(f".{uuid.uuid4().hex}.tmp")

            # Save file atomically
            await run_in_threadpool(tmp_path.write_bytes, processed_io.read())
            await run_in_threadpool(tmp_path.replace, save_path)

            logger.info(
                "image_saved_successfully",
                filename=filename,
                path=str(save_path),
                size=save_path.stat().st_size
            )

            # Return relative path (matching your DB storage format)
            return str(save_path)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("file_save_error", error=str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file"
            )

    @staticmethod
    def delete_image(image_path: str) -> bool:
        """Delete image file synchronously."""
        try:
            file_path = Path(image_path)
            if file_path.exists():
                file_path.unlink()
                logger.info("file_deleted", path=image_path)
                return True
            else:
                logger.warning("file_not_found_for_deletion", path=image_path)
                return False
        except Exception as e:
            logger.error("file_delete_error", path=image_path, error=str(e))
            return False

    @staticmethod
    def get_image_url(image_path: str, request_base_url: str) -> str:
        """Generate a public URL for an image file."""
        # Remove any leading path components and use just the filename
        filename = Path(image_path).name
        return f"{request_base_url.rstrip('/')}/uploads/{filename}"