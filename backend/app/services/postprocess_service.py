from __future__ import annotations

import base64
import io
import mimetypes
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import HTTPException
from PIL import Image, ImageColor, ImageDraw, ImageFont

from ..schemas import PostprocessImageRequest
from .image_provider import ImageProviderService
from .image_record_service import ImageRecordService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"
UPLOAD_DIR = PROJECT_ROOT / "app" / "uploads"


class PostprocessService:
    _FONT_CANDIDATES = (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "arial.ttf",
    )
    _LOGO_POSITION_EN = {
        "top_left": "top-left",
        "top_right": "top-right",
        "bottom_left": "bottom-left",
        "bottom_right": "bottom-right",
    }
    _LOGO_POSITION_ZH = {
        "top_left": "左上角",
        "top_right": "右上角",
        "bottom_left": "左下角",
        "bottom_right": "右下角",
    }

    _DATA_URI_MAX_BYTES = 10 * 1024 * 1024
    _DATA_URI_SAFE_BYTES = int(_DATA_URI_MAX_BYTES * 0.92)
    _JPEG_QUALITIES = (90, 82, 74, 66, 58, 50, 42)
    _RESIZE_FACTORS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4)

    @staticmethod
    def _resolve_uploaded_file(upload_dir: Path, image_id: str, *, label: str) -> Path:
        matches = list(upload_dir.glob(f"{image_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail=f"{label} invalid or file missing")
        return matches[0]

    @staticmethod
    def _resolve_logo_file(upload_dir: Path, logo_id: str) -> Path:
        return PostprocessService._resolve_uploaded_file(upload_dir, logo_id, label="logo_id")

    @staticmethod
    def _resolve_qr_file(upload_dir: Path, qr_id: str) -> Path:
        return PostprocessService._resolve_uploaded_file(upload_dir, qr_id, label="qr_image_id")

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
    def _path_to_data_url(path: Path) -> str:
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "image/png"
        payload = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{payload}"

    @staticmethod
    def _data_url_size(value: str) -> int:
        return len(value.encode("utf-8"))

    @staticmethod
    def _build_data_url(raw: bytes, mime: str) -> str:
        payload = base64.b64encode(raw).decode("utf-8")
        return f"data:{mime};base64,{payload}"

    @staticmethod
    def _path_to_data_url_limited(path: Path) -> str:
        raw_data_url = PostprocessService._path_to_data_url(path)
        if PostprocessService._data_url_size(raw_data_url) <= PostprocessService._DATA_URI_SAFE_BYTES:
            return raw_data_url

        image = Image.open(path)
        try:
            use_png = "A" in image.getbands()
            working = image.convert("RGBA" if use_png else "RGB")
            base_w, base_h = working.size

            best_data_url = raw_data_url
            best_size = PostprocessService._data_url_size(raw_data_url)

            for factor in PostprocessService._RESIZE_FACTORS:
                if factor == 1.0:
                    candidate = working
                else:
                    target_w = max(1, int(base_w * factor))
                    target_h = max(1, int(base_h * factor))
                    candidate = working.resize((target_w, target_h), Image.LANCZOS)

                try:
                    if use_png:
                        buf = io.BytesIO()
                        candidate.save(buf, format="PNG", optimize=True)
                        data_url = PostprocessService._build_data_url(buf.getvalue(), "image/png")
                        size = PostprocessService._data_url_size(data_url)
                        if size < best_size:
                            best_data_url = data_url
                            best_size = size
                        if size <= PostprocessService._DATA_URI_SAFE_BYTES:
                            return data_url
                    else:
                        for quality in PostprocessService._JPEG_QUALITIES:
                            buf = io.BytesIO()
                            candidate.save(
                                buf,
                                format="JPEG",
                                optimize=True,
                                quality=quality,
                                progressive=True,
                            )
                            data_url = PostprocessService._build_data_url(buf.getvalue(), "image/jpeg")
                            size = PostprocessService._data_url_size(data_url)
                            if size < best_size:
                                best_data_url = data_url
                                best_size = size
                            if size <= PostprocessService._DATA_URI_SAFE_BYTES:
                                return data_url
                finally:
                    if candidate is not working:
                        candidate.close()

            if best_size <= PostprocessService._DATA_URI_MAX_BYTES:
                return best_data_url
            raise HTTPException(
                status_code=400,
                detail=(
                    f"reference image too large after compression: {path.name}, "
                    f"data_uri_bytes={best_size}, limit={PostprocessService._DATA_URI_MAX_BYTES}"
                ),
            )
        finally:
            image.close()

    @staticmethod
    def _is_data_uri_too_large_error(exc: HTTPException) -> bool:
        detail = str(exc.detail)
        return exc.status_code == 400 and (
            "BadRequest.TooLarge" in detail
            or "Exceeded limit on max bytes per data-uri item" in detail
        )

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
    def _apply_qr_phone_card(
        base_image: Image.Image,
        qr_path: Path,
        *,
        position: str,
        scale: float,
        phone_number: str,
        card_opacity: float,
    ) -> None:
        qr_image = Image.open(qr_path).convert("RGBA")
        image_w, image_h = base_image.size
        min_dim = min(image_w, image_h)

        qr_size = max(72, min(int(min_dim * scale), int(min_dim * 0.42)))
        qr_resized = qr_image.resize((qr_size, qr_size), Image.LANCZOS)

        card_padding = max(10, int(qr_size * 0.12))
        inner_gap = max(6, int(qr_size * 0.08))
        phone = phone_number.strip()
        font_size = max(14, int(qr_size * 0.16))
        font = PostprocessService._load_font(font_size)

        temp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp)
        text_w = 0
        text_h = 0
        if phone:
            text_box = temp_draw.textbbox((0, 0), phone, font=font, stroke_width=0)
            text_w = max(1, text_box[2] - text_box[0])
            text_h = max(1, text_box[3] - text_box[1])

        card_w = qr_size + card_padding * 2
        card_h = qr_size + card_padding * 2
        if phone:
            card_h += inner_gap + text_h
            card_w = max(card_w, text_w + card_padding * 2)

        outer_padding = max(10, int(min_dim * 0.03))
        x = outer_padding if position == "bottom_left" else image_w - card_w - outer_padding
        y = image_h - card_h - outer_padding
        x = max(outer_padding, x)
        y = max(outer_padding, y)

        layer = Image.new("RGBA", (image_w, image_h), (0, 0, 0, 0))
        drawer = ImageDraw.Draw(layer)
        radius = max(10, int(card_w * 0.07))
        shadow_alpha = max(35, int(90 * card_opacity))
        bg_alpha = max(80, int(238 * card_opacity))
        border_alpha = max(25, int(52 * card_opacity))

        drawer.rounded_rectangle(
            [x + 2, y + 3, x + card_w + 2, y + card_h + 3],
            radius=radius,
            fill=(0, 0, 0, shadow_alpha),
        )
        drawer.rounded_rectangle(
            [x, y, x + card_w, y + card_h],
            radius=radius,
            fill=(255, 255, 255, bg_alpha),
            outline=(0, 0, 0, border_alpha),
            width=max(1, int(card_w * 0.012)),
        )

        qr_x = x + (card_w - qr_size) // 2
        qr_y = y + card_padding
        drawer.rounded_rectangle(
            [qr_x - 2, qr_y - 2, qr_x + qr_size + 2, qr_y + qr_size + 2],
            radius=max(4, int(qr_size * 0.05)),
            fill=(255, 255, 255, min(255, int(250 * card_opacity))),
        )
        layer.alpha_composite(qr_resized, (qr_x, qr_y))

        if phone:
            text_x = x + (card_w - text_w) // 2
            text_y = qr_y + qr_size + inner_gap
            drawer.text(
                (text_x, text_y),
                phone,
                font=font,
                fill=(24, 24, 24, min(255, int(248 * card_opacity))),
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
            position_en = PostprocessService._LOGO_POSITION_EN.get(req.logo_position, "bottom-right")
            position_zh = PostprocessService._LOGO_POSITION_ZH.get(req.logo_position, "右下角")
            prompt = (
                f"{prompt}\n"
                "Two reference images are provided: first is the original image, second is the logo image. "
                "Keep the original composition and style, and blend the logo naturally. "
                f"Place exactly one logo at the {position_en} corner with a small margin from edges, "
                "do not place it in other corners.\n"
                f"请将 logo 固定放在{position_zh}，与画面边缘保持小间距，只出现一个 logo，不要放在其他位置。"
            )

        try:
            generated = await ImageProviderService.generate_image(
                api_key=req.api_key or "",
                base_url=req.base_url,
                model=req.model,
                prompt=prompt,
                ratio_key=req.ai_ratio_key,
                logo_base64_data_url=None,
                reference_images_data_urls=references,
            )
        except HTTPException as exc:
            if not PostprocessService._is_data_uri_too_large_error(exc):
                raise

            compressed_refs = [PostprocessService._path_to_data_url_limited(source_path)]
            if logo_file:
                compressed_refs.append(PostprocessService._path_to_data_url_limited(logo_file))

            generated = await ImageProviderService.generate_image(
                api_key=req.api_key or "",
                base_url=req.base_url,
                model=req.model,
                prompt=prompt,
                ratio_key=req.ai_ratio_key,
                logo_base64_data_url=None,
                reference_images_data_urls=compressed_refs,
            )
        local_path = await PostprocessService._ensure_local_image_path(generated)
        return f"/static/generated/{local_path.name}"

    @staticmethod
    def list_generated_images(limit: int = 200) -> list[dict]:
        return ImageRecordService.list_generated_images(limit=limit)

    @staticmethod
    def mark_generated_image_deleted(source_path: str) -> dict:
        return ImageRecordService.soft_delete_by_path(source_path)

    @staticmethod
    async def postprocess_images(req: PostprocessImageRequest, upload_dir: Path) -> dict:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        batch_id = uuid.uuid4().hex

        logo_file: Optional[Path] = None
        if req.logo_id:
            logo_file = PostprocessService._resolve_logo_file(upload_dir=upload_dir, logo_id=req.logo_id)
        qr_file: Optional[Path] = None
        if req.qr_enabled and req.qr_image_id:
            qr_file = PostprocessService._resolve_qr_file(upload_dir=upload_dir, qr_id=req.qr_image_id)

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

                    if qr_file:
                        PostprocessService._apply_qr_phone_card(
                            image,
                            qr_file,
                            position=req.qr_position,
                            scale=req.qr_scale,
                            phone_number=req.phone_number,
                            card_opacity=req.qr_card_opacity,
                        )

                    out_name = f"postprocessed_{uuid.uuid4().hex}.png"
                    out_path = GENERATED_DIR / out_name
                    image.convert("RGB").save(out_path, format="PNG", optimize=True)
                    saved_path = f"/static/generated/{out_name}"

                ImageRecordService.register_saved_image(
                    saved_path=saved_path,
                    source_type="postprocess",
                    source_batch_id=batch_id,
                    meta={"source_path": source_path, "process_mode": req.process_mode},
                )
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
