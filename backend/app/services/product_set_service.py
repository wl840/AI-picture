from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..prompt_engineering import PRODUCT_SET_TYPES, build_product_set_prompt
from ..schemas import GenerateProductSetRequest
from .image_provider import ImageProviderService
from .storage import StorageService


class ProductSetService:
    @staticmethod
    def _resolve_product_image_file(upload_dir: Path, product_image_id: str) -> Path:
        matches = list(upload_dir.glob(f"{product_image_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="product_image_id 无效或文件不存在")
        return matches[0]

    @staticmethod
    async def generate_product_set(req: GenerateProductSetRequest, upload_dir: Path) -> dict:
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
                items.append(
                    {
                        "key": image_type,
                        "name": image_name,
                        "prompt": prompt,
                        **generated,
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
