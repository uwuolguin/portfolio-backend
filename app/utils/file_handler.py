import asyncio
import structlog
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException, status

from app.config import settings
from app.services.image_processor import image_processor

logger = structlog.get_logger(__name__)


class FileHandler:
    UPLOAD_DIR = Path("uploads/company_images")

    @staticmethod
    def init_upload_directory() -> None:
        """Ensure upload directory exists."""
        FileHandler.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("upload_directory_initialized", path=str(FileHandler.UPLOAD_DIR))

    @staticmethod
    async def save_image(
        file: UploadFile,
        company_uuid: Optional[str] = None,
        check_nsfw: bool = True,
        public_base_url: Optional[str] = None,
    ) -> str:
        """
        Save and process an uploaded image with full validation and NSFW protection.

        Args:
            file: Uploaded file.
            company_uuid: Optional UUID for filename.
            check_nsfw: Whether to run DeepAI NSFW check.
            public_base_url: Base URL for constructing public image URL.

        Returns:
            str: Path to the saved image.

        Raises:
            HTTPException: If validation fails or NSFW content is detected.
        """
        try:
            result = await image_processor.process_and_save(
                file=file,
                upload_dir=FileHandler.UPLOAD_DIR,
                company_uuid=company_uuid,
                check_nsfw=check_nsfw,
                public_base_url=public_base_url or settings.api_base_url + "/uploads/company_images",
            )

            # Handle NSFW flagged image
            if result.get("nsfw_flagged"):
                saved_path = Path(result["path"])
                if saved_path.exists():
                    await asyncio.get_event_loop().run_in_executor(None, saved_path.unlink)

                nsfw_info = result.get("nsfw_check", {})
                confidence = nsfw_info.get("confidence", "unknown")

                logger.warning(
                    "nsfw_image_rejected",
                    filename=result["filename"],
                    confidence=confidence,
                    provider="deepai",
                )

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image contains inappropriate content and cannot be uploaded",
                )

            logger.info(
                "image_saved_successfully",
                filename=result["filename"],
                size=result["size"],
                nsfw_checked=check_nsfw,
            )

            return result["path"]

        except HTTPException:
            raise  # already handled exceptions
        except Exception as e:
            logger.error("file_save_error", error=str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file",
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
        return f"{request_base_url.rstrip('/')}/{str(image_path).lstrip('/')}"