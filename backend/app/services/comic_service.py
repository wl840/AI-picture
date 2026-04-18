from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import HTTPException
from PIL import Image

from ..poster_config import ASPECT_RATIOS
from ..prompt_engineering import _build_panel_scenes, build_comic_panel_prompt
from ..schemas import GenerateComicRequest
from .image_provider import ImageProviderService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"


def _path_to_data_url(local_path: Path) -> str:
    data = base64.b64encode(local_path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{data}"


async def _download_to_local(image_url: str) -> Path:
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.get(image_url)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"下载漫画格图片失败: status={resp.status_code}")
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_DIR / f"comic_panel_remote_{uuid.uuid4().hex}.png"
    out.write_bytes(resp.content)
    return out


async def _ensure_local_path(image: dict) -> Path:
    if image.get("saved_path"):
        file_name = str(image["saved_path"]).rsplit("/", 1)[-1]
        local_path = GENERATED_DIR / file_name
        if local_path.exists():
            return local_path

    if image.get("image_base64"):
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        out = GENERATED_DIR / f"comic_panel_b64_{uuid.uuid4().hex}.png"
        out.write_bytes(base64.b64decode(image["image_base64"]))
        return out

    if image.get("image_url"):
        return await _download_to_local(image["image_url"])

    raise HTTPException(status_code=502, detail="无法定位漫画格图片文件")


def compose_comic_strip(panel_paths: list[Path], panel_count: int) -> str:
    """将各格图片拼合为漫画条，返回本地文件路径（相对 static 的 URL 路径由调用方构造）。"""
    panels = [Image.open(p).convert("RGB") for p in panel_paths]
    pw, ph = panels[0].size

    gutter = 20
    border = 30

    if panel_count == 4:
        cols, rows = 2, 2
    elif panel_count == 5:
        cols, rows = 2, 3
    else:  # 6
        cols, rows = 2, 3

    total_w = cols * pw + (cols + 1) * gutter + 2 * border
    total_h = rows * ph + (rows + 1) * gutter + 2 * border

    composite = Image.new("RGB", (total_w, total_h), color=(255, 255, 255))

    for i, panel in enumerate(panels):
        row = i // cols
        col = i % cols

        if panel_count == 5 and i == 4:
            x = (total_w - pw) // 2
        else:
            x = border + col * (pw + gutter) + gutter

        y = border + row * (ph + gutter) + gutter
        composite.paste(panel, (x, y))

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"comic_strip_{uuid.uuid4().hex}.png"
    out_path = GENERATED_DIR / out_name
    composite.save(out_path, format="PNG", optimize=True)
    return f"/static/generated/{out_name}"


class ComicService:
    @staticmethod
    async def generate_comic(req: GenerateComicRequest) -> dict:
        ratio = ASPECT_RATIOS.get(req.ratio_key, ASPECT_RATIOS["square"])
        scenes = _build_panel_scenes(req.panel_count)
        panels = []
        last_data_url: Optional[str] = None
        local_paths: list[Path] = []

        for i, scene in enumerate(scenes):
            prompt = build_comic_panel_prompt(
                panel_index=i + 1,
                panel_count=req.panel_count,
                product_name=req.product_name,
                scene_description=scene,
                style=req.style,
                character_hint=req.character_description,
                ratio_label=ratio["label"],
                ratio_size=ratio["size"],
            )

            reference_images = [last_data_url] if last_data_url else []

            try:
                image = await ImageProviderService.generate_image(
                    api_key=req.api_key,
                    base_url=req.base_url,
                    model=req.model,
                    prompt=prompt,
                    ratio_key=req.ratio_key,
                    logo_base64_data_url=None,
                    reference_images_data_urls=reference_images,
                )
                local_path = await _ensure_local_path(image)
                local_paths.append(local_path)
                last_data_url = _path_to_data_url(local_path)

                panels.append({
                    "index": i + 1,
                    "scene": scene,
                    "prompt": prompt,
                    "saved_path": f"/static/generated/{local_path.name}",
                    "error": None,
                })
            except Exception as exc:
                panels.append({
                    "index": i + 1,
                    "scene": scene,
                    "prompt": prompt,
                    "error": str(exc),
                })

        composite_path: Optional[str] = None
        if local_paths:
            composite_path = compose_comic_strip(local_paths, req.panel_count)

        return {
            "panel_count": req.panel_count,
            "panels": panels,
            "composite_path": composite_path,
        }
