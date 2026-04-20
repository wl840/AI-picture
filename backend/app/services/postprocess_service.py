from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import HTTPException
from PIL import Image, ImageColor, ImageDraw, ImageFont

from ..schemas import PostprocessImageRequest
from .image_provider import ImageProviderService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"
UPLOAD_DIR = PROJECT_ROOT / "app" / "uploads"
SOFT_DELETE_MARK_FILE = GENERATED_DIR / "generated_images_soft_deleted.json"


class PostprocessService:
    _FONT_CANDIDATES = (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "arial.ttf",
    )

    @staticmethod
    def _resolve_logo_file(upload_dir: Path, logo_id: str) -> Path:
        matches = list(upload_dir.glob(f"{logo_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="logo_id invalid or file missing")
        return matches[0]

    @staticmethod
    def _resolve_source_path(source_path: str) -> Path:
        value = source_path.strip()
        if value.startswith("/static/generated/"):
            local_path = GENERATED_DIR / value.rsplit("/", 1)[-1]
        elif value.startswith("/static/uploads/"):
            local_path = UPLOAD_DIR / value.rsplit("/", 1)[-1]
        else:
            raise HTTPException(status_code=400, detail=f"unsupported image path: {value}")

        if not local_path.exists():
            raise HTTPException(status_code=404, detail=f"image not found: {value}")
        return local_path

    @staticmethod
    def _normalize_generated_static_path(source_path: str) -> str:
        value = source_path.strip()
        if not value.startswith("/static/generated/"):
            raise HTTPException(status_code=400, detail=f"unsupported generated image path: {value}")

        filename = value.rsplit("/", 1)[-1]
        if not filename:
            raise HTTPException(status_code=400, detail=f"invalid generated image path: {value}")
        return f"/static/generated/{filename}"

    @staticmethod
    def _load_soft_deleted_map() -> dict[str, str]:
        if not SOFT_DELETE_MARK_FILE.exists():
            return {}
        try:
            data = json.loads(SOFT_DELETE_MARK_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if isinstance(k, str)}

    @staticmethod
    def _save_soft_deleted_map(deleted_map: dict[str, str]) -> None:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        SOFT_DELETE_MARK_FILE.write_text(
            json.dumps(deleted_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _path_to_data_url(path: Path) -> str:
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "image/png"
        payload = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{payload}"

    @staticmethod
    async def _download_remote_image(image_url: str) -> Path:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.get(image_url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"download remote image failed: status={response.status_code}")

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        out = GENERATED_DIR / f"postprocess_ai_remote_{uuid.uuid4().hex}.png"
        out.write_bytes(response.content)
        return out

    @staticmethod
    def _load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        size = max(12, font_size)
        for candidate in PostprocessService._FONT_CANDIDATES:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _anchor_xy(
        *,
        image_w: int,
        image_h: int,
        box_w: int,
        box_h: int,
        position: str,
        padding: int,
    ) -> tuple[int, int]:
        if position == "top_left":
            return padding, padding
        if position == "top_right":
            return image_w - box_w - padding, padding
        if position == "bottom_left":
            return padding, image_h - box_h - padding
        if position == "center":
            return max((image_w - box_w) // 2, padding), max((image_h - box_h) // 2, padding)
        return image_w - box_w - padding, image_h - box_h - padding

    @staticmethod
    def _color_with_alpha(color: str, opacity: float) -> tuple[int, int, int, int]:
        try:
            rgb = ImageColor.getrgb(color)
        except ValueError:
            rgb = (255, 255, 255)
        alpha = max(0, min(255, int(255 * opacity)))
        return rgb[0], rgb[1], rgb[2], alpha

    @staticmethod
    def _apply_logo(
        base_image: Image.Image,
        logo_path: Path,
        *,
        position: str,
        scale: float,
        opacity: float,
    ) -> None:
        logo = Image.open(logo_path).convert("RGBA")
        base_w, base_h = base_image.size
        logo_w, logo_h = logo.size

        max_w = max(1, int(base_w * scale))
        max_h = max(1, int(base_h * scale))
        ratio = min(max_w / logo_w, max_h / logo_h, 1.0)
        target_w = max(1, int(logo_w * ratio))
        target_h = max(1, int(logo_h * ratio))
        resized = logo.resize((target_w, target_h), Image.LANCZOS)

        if opacity < 1.0:
            alpha = resized.split()[3].point(lambda p: int(p * opacity))
            resized.putalpha(alpha)

        padding = max(8, int(min(base_w, base_h) * 0.02))
        x, y = PostprocessService._anchor_xy(
            image_w=base_w,
            image_h=base_h,
            box_w=target_w,
            box_h=target_h,
            position=position,
            padding=padding,
        )
        base_image.alpha_composite(resized, (x, y))

    @staticmethod
    def _draw_text_overlay(
        base_image: Image.Image,
        *,
        text: str,
        position: str,
        font_scale: float,
        opacity: float,
        color: str,
        draw_bg: bool,
    ) -> None:
        if not text.strip():
            return

        width, height = base_image.size
        font_size = max(12, int(min(width, height) * font_scale))
        font = PostprocessService._load_font(font_size)
        stroke_width = max(1, font_size // 16)
        padding = max(8, font_size // 3)

        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        drawer = ImageDraw.Draw(layer)
        bbox = drawer.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

        x, y = PostprocessService._anchor_xy(
            image_w=width,
            image_h=height,
            box_w=text_w,
            box_h=text_h,
            position=position,
            padding=padding,
        )

        if draw_bg:
            bg_alpha = min(0.8, opacity * 0.45)
            drawer.rounded_rectangle(
                [x - padding, y - padding, x + text_w + padding, y + text_h + padding],
                radius=max(8, padding // 2),
                fill=(0, 0, 0, int(255 * bg_alpha)),
            )

        drawer.text(
            (x, y),
            text,
            font=font,
            fill=PostprocessService._color_with_alpha(color=color, opacity=opacity),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, min(255, int(255 * max(0.4, opacity)))),
        )
        base_image.alpha_composite(layer)

    @staticmethod
    async def _ensure_local_image_path(generated: dict) -> Path:
        if generated.get("saved_path"):
            file_name = str(generated["saved_path"]).rsplit("/", 1)[-1]
            local_path = GENERATED_DIR / file_name
            if local_path.exists():
                return local_path

        if generated.get("image_base64"):
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            out = GENERATED_DIR / f"postprocess_ai_b64_{uuid.uuid4().hex}.png"
            out.write_bytes(base64.b64decode(generated["image_base64"]))
            return out

        if generated.get("image_url"):
            return await PostprocessService._download_remote_image(generated["image_url"])

        raise HTTPException(status_code=502, detail="AI postprocess did not return a usable local image")

    @staticmethod
    async def _postprocess_with_ai(
        *,
        req: PostprocessImageRequest,
        source_path: Path,
        logo_file: Optional[Path],
    ) -> str:
        references = [PostprocessService._path_to_data_url(source_path)]
        if logo_file:
            references.append(PostprocessService._path_to_data_url(logo_file))

        prompt = req.ai_prompt.strip()
        if logo_file:
            prompt = (
                f"{prompt}\n"
                "Two reference images are provided: first is the original image, second is the logo image. "
                "Keep the original composition and style, and blend the logo naturally."
            )

        generated = await ImageProviderService.generate_image(
            api_key=req.api_key or "",
            base_url=req.base_url,
            model=req.model,
            prompt=prompt,
            ratio_key=req.ai_ratio_key,
            logo_base64_data_url=None,
            reference_images_data_urls=references,
        )
        local_path = await PostprocessService._ensure_local_image_path(generated)
        return f"/static/generated/{local_path.name}"

    @staticmethod
    def list_generated_images(limit: int = 200) -> list[dict]:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        soft_deleted_map = PostprocessService._load_soft_deleted_map()
        soft_deleted_paths = set(soft_deleted_map.keys())
        candidates = [
            p
            for p in GENERATED_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        visible_candidates = []
        for p in candidates:
            static_path = f"/static/generated/{p.name}"
            if static_path in soft_deleted_paths:
                continue
            visible_candidates.append((p, static_path))

        items = []
        for p, static_path in visible_candidates[:limit]:
            stat = p.stat()
            items.append(
                {
                    "path": static_path,
                    "filename": p.name,
                    "modified_at": stat.st_mtime,
                    "size_bytes": stat.st_size,
                }
            )
        return items

    @staticmethod
    def mark_generated_image_deleted(source_path: str) -> dict:
        normalized_path = PostprocessService._normalize_generated_static_path(source_path)
        local_path = GENERATED_DIR / normalized_path.rsplit("/", 1)[-1]
        if not local_path.exists():
            raise HTTPException(status_code=404, detail=f"image not found: {normalized_path}")

        deleted_map = PostprocessService._load_soft_deleted_map()
        deleted_at = deleted_map.get(normalized_path) or datetime.now(timezone.utc).isoformat()
        deleted_map[normalized_path] = deleted_at
        PostprocessService._save_soft_deleted_map(deleted_map)
        return {"ok": True, "path": normalized_path, "deleted_at": deleted_at}

    @staticmethod
    async def postprocess_images(req: PostprocessImageRequest, upload_dir: Path) -> dict:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

        logo_file: Optional[Path] = None
        if req.logo_id:
            logo_file = PostprocessService._resolve_logo_file(upload_dir=upload_dir, logo_id=req.logo_id)

        items: list[dict] = []
        for source_path in req.image_paths:
            try:
                local_source = PostprocessService._resolve_source_path(source_path)
                if req.process_mode == "ai":
                    saved_path = await PostprocessService._postprocess_with_ai(
                        req=req,
                        source_path=local_source,
                        logo_file=logo_file,
                    )
                else:
                    image = Image.open(local_source).convert("RGBA")

                    if logo_file:
                        PostprocessService._apply_logo(
                            image,
                            logo_file,
                            position=req.logo_position,
                            scale=req.logo_scale,
                            opacity=req.logo_opacity,
                        )

                    if req.watermark_text:
                        PostprocessService._draw_text_overlay(
                            image,
                            text=req.watermark_text,
                            position=req.watermark_position,
                            font_scale=req.watermark_font_scale,
                            opacity=req.watermark_opacity,
                            color=req.watermark_color,
                            draw_bg=False,
                        )

                    if req.text_content:
                        PostprocessService._draw_text_overlay(
                            image,
                            text=req.text_content,
                            position=req.text_position,
                            font_scale=req.text_font_scale,
                            opacity=req.text_opacity,
                            color=req.text_color,
                            draw_bg=True,
                        )

                    out_name = f"postprocessed_{uuid.uuid4().hex}.png"
                    out_path = GENERATED_DIR / out_name
                    image.convert("RGB").save(out_path, format="PNG", optimize=True)
                    saved_path = f"/static/generated/{out_name}"

                items.append({"source_path": source_path, "saved_path": saved_path, "error": None})
            except HTTPException as exc:
                items.append({"source_path": source_path, "saved_path": None, "error": str(exc.detail)})
            except Exception as exc:  # noqa: BLE001
                items.append({"source_path": source_path, "saved_path": None, "error": str(exc)})

        success_count = sum(1 for item in items if item.get("saved_path"))
        if success_count == 0:
            sample_errors = [item.get("error") for item in items if item.get("error")]
            sample_errors = [err for err in sample_errors if err][:3]
            detail = {"message": "postprocess failed for all images", "sample_errors": sample_errors}
            raise HTTPException(status_code=502, detail=detail)

        return {"success_count": success_count, "items": items}
