from __future__ import annotations

import base64
import uuid
from pathlib import Path

import httpx
from fastapi import HTTPException

from ..prompt_engineering import PRODUCT_SET_TYPES, build_product_set_prompt
from ..schemas import GenerateProductSetRequest
from .image_provider import ImageProviderService
from .image_record_service import ImageRecordService
from .storage import StorageService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"


class ProductSetService:
    @staticmethod
    def _resolve_product_image_file(upload_dir: Path, product_image_id: str) -> Path:
        matches = list(upload_dir.glob(f"{product_image_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="product_image_id 无效或文件不存在")
        return matches[0]

    @staticmethod
    async def _download_remote_image(image_url: str) -> Path:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.get(image_url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"download remote image failed: status={response.status_code}")

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        out = GENERATED_DIR / f"product_set_remote_{uuid.uuid4().hex}.png"
        out.write_bytes(response.content)
        return out

    @staticmethod
    async def _ensure_local_saved_path(generated: dict) -> str:
        if generated.get("saved_path"):
            saved_path = str(generated["saved_path"]).strip()
            if saved_path.startswith("/static/generated/"):
                local_path = GENERATED_DIR / saved_path.rsplit("/", 1)[-1]
                if local_path.exists():
                    return saved_path

        if generated.get("image_base64"):
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            out = GENERATED_DIR / f"product_set_b64_{uuid.uuid4().hex}.png"
            out.write_bytes(base64.b64decode(generated["image_base64"]))
            return f"/static/generated/{out.name}"

        if generated.get("image_url"):
            out = await ProductSetService._download_remote_image(str(generated["image_url"]))
            return f"/static/generated/{out.name}"

        raise HTTPException(status_code=502, detail="无法定位五图生成文件用于记录")

    @staticmethod
    async def generate_product_set(req: GenerateProductSetRequest, upload_dir: Path) -> dict:
        batch_id = uuid.uuid4().hex
        product_image_path = ProductSetService._resolve_product_image_file(upload_dir, req.product_image_id)
        product_image_data_url = StorageService.file_to_data_url(product_image_path.name)
        if not product_image_data_url:
            raise HTTPException(status_code=404, detail="产品参考图不存在")

        items = []
        for image_type, image_name in PRODUCT_SET_TYPES.items():
            prompt = build_product_set_prompt(
                image_type=image_type,
                product_name=req.product_name,
                style=req.style,
                ratio_key=req.ratio_key,
                highlights=req.highlights,
                description=req.description,
                scene_description=req.scene_description,
                specs=req.specs,
            )

            try:
                generated = await ImageProviderService.generate_image(
                    api_key=req.api_key,
                    base_url=req.base_url,
                    model=req.model,
                    prompt=prompt,
                    ratio_key=req.ratio_key,
                    reference_images_data_urls=[product_image_data_url],
                )
                saved_path = await ProductSetService._ensure_local_saved_path(generated)
                ImageRecordService.register_saved_image(
                    saved_path=saved_path,
                    source_type="product_set",
                    source_batch_id=batch_id,
                    source_slot=image_type,
                    meta={
                        "product_image_id": req.product_image_id,
                        "ratio_key": req.ratio_key,
                        "style": req.style,
                    },
                )
                items.append(
                    {
                        "key": image_type,
                        "name": image_name,
                        "prompt": prompt,
                        **generated,
                        "saved_path": saved_path,
                    }
                )
            except HTTPException as exc:
                items.append(
                    {
                        "key": image_type,
                        "name": image_name,
                        "prompt": prompt,
                        "error": str(exc.detail),
                    }
                )

        success_count = sum(1 for item in items if not item.get("error"))
        if success_count == 0:
            raise HTTPException(status_code=502, detail="五图全部生成失败，请检查模型配置或稍后重试")

        return {
            "product_image_id": req.product_image_id,
            "success_count": success_count,
            "items": items,
        }
