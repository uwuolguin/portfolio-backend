import uuid
import asyncio
import structlog
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from app.config import settings

logger = structlog.get_logger(__name__)


class FileHandler:
    UPLOAD_DIR = Path("uploads/company_images")

    @staticmethod
    def init_upload_directory():
        FileHandler.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("upload_directory_initialized", path=str(FileHandler.UPLOAD_DIR))

    @staticmethod
    async def validate_image(file: UploadFile) -> None:
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )

        if file.content_type not in settings.allowed_file_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: {', '.join(settings.allowed_file_types)}"
            )
        extension = Path(file.filename).suffix.lower()
        allowed_extensions = {".jpeg", ".png"}
        if extension not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}"
            )

        logger.debug("file_validated", filename=file.filename, content_type=file.content_type)

    @staticmethod
    async def save_image(file: UploadFile, company_uuid: Optional[str] = None) -> str:
        await FileHandler.validate_image(file)

        file_extension = Path(file.filename).suffix.lower()
        filename = f"{company_uuid or uuid.uuid4()}{file_extension}"
        file_path = FileHandler.UPLOAD_DIR / filename

        try:
            content = await file.read()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, file_path.write_bytes, content)

            logger.info("file_saved", filename=filename, size=len(content))
            return str(file_path.resolve())

        except Exception as e:
            logger.error("file_save_error", error=str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file"
            )

    @staticmethod
    def delete_image(image_path: str) -> bool:
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
        return f"{request_base_url.rstrip('/')}/{str(image_path).lstrip('/')}"
