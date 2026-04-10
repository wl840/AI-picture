from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import HTTPException

from ..prompt_engineering import build_poster_prompt
from ..schemas import GeneratePosterRequest
from .image_postprocess import add_logo_to_image
from .image_provider import ImageProviderService
from .storage import StorageService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"


class PosterService:
    @staticmethod
    def _resolve_logo_file(upload_dir: Path, logo_id: str) -> Path:
        matches = list(upload_dir.glob(f"{logo_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="logo_id 无效或文件不存在")
        return matches[0]

    @staticmethod
    async def _download_remote_image(image_url: str) -> Path:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.get(image_url)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"下载模型返回图片失败: status={resp.status_code}",
            )

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        out = GENERATED_DIR / f"generated_remote_{uuid.uuid4().hex}.png"
        out.write_bytes(resp.content)
        return out

    @staticmethod
    async def _ensure_local_image_path(generated: dict) -> Path:
        if generated.get("saved_path"):
            file_name = str(generated["saved_path"]).rsplit("/", 1)[-1]
            local_path = GENERATED_DIR / file_name
            if local_path.exists():
                return local_path

        if generated.get("image_base64"):
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            out = GENERATED_DIR / f"generated_b64_{uuid.uuid4().hex}.png"
            out.write_bytes(base64.b64decode(generated["image_base64"]))
            return out

        if generated.get("image_url"):
            return await PosterService._download_remote_image(generated["image_url"])

        raise HTTPException(status_code=502, detail="无法定位生成海报文件用于后处理")

    @staticmethod
    async def generate_poster(req: GeneratePosterRequest, upload_dir: Path) -> dict:
        logo_filename: Optional[str] = None
        logo_file_path: Optional[Path] = None

        if req.logo_id:
            logo_file_path = PosterService._resolve_logo_file(upload_dir, req.logo_id)
            logo_filename = logo_file_path.name

        prompt = build_poster_prompt(
            template_key=req.template_key,
            product_name=req.product_name,
            highlights=req.highlights,
            style=req.style,
            description=req.description,
            ratio_key=req.ratio_key,
            logo_mode=req.logo_mode,
            logo_position=req.logo_position,
            logo_filename=logo_filename,
        )

        # fixed 模式：明确禁止把 logo 传给模型，仅生成商品海报。
        if req.logo_mode == "fixed":
            logo_base64_data_url = None
        else:
            logo_base64_data_url = (
                StorageService.logo_to_data_url(logo_filename)
                if logo_filename
                else None
            )

        image = await ImageProviderService.generate_image(
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
            prompt=prompt,
            ratio_key=req.ratio_key,
            logo_base64_data_url=logo_base64_data_url,
        )

        # fixed 模式：模型只出商品图，后端贴 logo（稳定可控）
        if req.logo_mode == "fixed" and logo_file_path:
            base_poster_path = await PosterService._ensure_local_image_path(image)
            merged_path = add_logo_to_image(
                image_path=str(base_poster_path),
                logo_path=str(logo_file_path),
                position=req.logo_position or "top_right",
            )
            return {
                "prompt": prompt,
                "saved_path": f"/static/generated/{Path(merged_path).name}",
            }

        # ai 模式：保持原有模型融合结果
        return {"prompt": prompt, **image}
