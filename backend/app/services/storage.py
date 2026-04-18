from __future__ import annotations

import base64
import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = PROJECT_ROOT / "app" / "uploads"


class StorageService:
    @staticmethod
    async def _save_image(file: UploadFile, *, invalid_message: str) -> tuple[str, str]:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=invalid_message)

        suffix = Path(file.filename or "image.png").suffix or ".png"
        image_id = uuid.uuid4().hex
        filename = f"{image_id}{suffix}"
        target = UPLOAD_DIR / filename
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        target.write_bytes(content)
        return image_id, filename

    @staticmethod
    async def save_logo(file: UploadFile) -> tuple[str, str]:
        return await StorageService._save_image(file, invalid_message="仅支持图片格式 logo")

    @staticmethod
    async def save_product_image(file: UploadFile) -> tuple[str, str]:
        return await StorageService._save_image(file, invalid_message="仅支持图片格式产品图")

    @staticmethod
    def file_to_data_url(filename: str) -> str | None:
        file_path = UPLOAD_DIR / filename
        if not file_path.exists():
            return None

        mime, _ = mimetypes.guess_type(file_path.name)
        mime = mime or "image/png"
        data = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{data}"

    @staticmethod
    def logo_to_data_url(logo_filename: str) -> str | None:
        return StorageService.file_to_data_url(logo_filename)
