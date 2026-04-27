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
    _MAX_REFERENCE_EDGE = 7900
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
        image = Image.open(path)
        try:
            use_png = "A" in image.getbands()
            working = image.convert("RGBA" if use_png else "RGB")
            base_w, base_h = working.size

            edge_scale = min(
                1.0,
                PostprocessService._MAX_REFERENCE_EDGE / max(1, base_w),
                PostprocessService._MAX_REFERENCE_EDGE / max(1, base_h),
            )
            if edge_scale < 1.0:
                constrained_w = max(1, int(base_w * edge_scale))
                constrained_h = max(1, int(base_h * edge_scale))
                base_image = working.resize((constrained_w, constrained_h), Image.LANCZOS)
            else:
                base_image = working

            try:
                best_data_url = ""
                best_size = 1 << 60

                for factor in PostprocessService._RESIZE_FACTORS:
                    if factor == 1.0:
                        candidate = base_image
                    else:
                        target_w = max(1, int(base_image.size[0] * factor))
                        target_h = max(1, int(base_image.size[1] * factor))
                        candidate = base_image.resize((target_w, target_h), Image.LANCZOS)

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
                        if candidate is not base_image:
                            candidate.close()

                if best_size <= PostprocessService._DATA_URI_MAX_BYTES:
                    return best_data_url
            finally:
                if base_image is not working:
                    base_image.close()

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
    def _resolve_ai_layout_mode(req_mode: str, image_w: int, image_h: int) -> str:
        if req_mode in {"single", "comic_4", "comic_6"}:
            return req_mode
        ratio = image_h / max(1, image_w)
        if ratio >= 2.0:
            return "comic_6"
        if ratio >= 1.25:
            return "comic_4"
        if ratio <= 0.72:
            return "comic_6"
        if ratio <= 0.95:
            return "comic_4"
        return "single"

    @staticmethod
    def _sample_avg_color(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
        x1, y1, x2, y2 = box
        x1 = max(0, min(image.width - 1, x1))
        y1 = max(0, min(image.height - 1, y1))
        x2 = max(x1 + 1, min(image.width, x2))
        y2 = max(y1 + 1, min(image.height, y2))
        region = image.crop((x1, y1, x2, y2)).convert("RGB")
        avg = region.resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
        return int(avg[0]), int(avg[1]), int(avg[2])

    @staticmethod
    def _build_ai_brand_canvas(source_path: Path, req: PostprocessImageRequest) -> tuple[Path, dict]:
        src = Image.open(source_path).convert("RGB")
        try:
            src_w, src_h = src.size
            layout_mode = PostprocessService._resolve_ai_layout_mode(req.ai_layout_mode, src_w, src_h)
            if layout_mode == "comic_6":
                top_ratio, bottom_ratio = 0.15, 0.23
            elif layout_mode == "comic_4":
                top_ratio, bottom_ratio = 0.13, 0.20
            else:
                top_ratio, bottom_ratio = 0.14, 0.18

            top_margin = max(88, int(src_h * top_ratio))
            bottom_margin = max(120, int(src_h * bottom_ratio))
            canvas_w = src_w
            canvas_h = src_h + top_margin + bottom_margin

            top_color = PostprocessService._sample_avg_color(src, (0, 0, src_w, max(1, int(src_h * 0.12))))
            bottom_color = PostprocessService._sample_avg_color(
                src,
                (0, max(0, int(src_h * 0.88)), src_w, src_h),
            )
            mix = (
                (top_color[0] + bottom_color[0]) // 2,
                (top_color[1] + bottom_color[1]) // 2,
                (top_color[2] + bottom_color[2]) // 2,
            )
            top_fill = tuple(min(255, int(v * 0.92 + 36)) for v in mix)
            bottom_fill = tuple(min(255, int(v * 0.88 + 44)) for v in mix)

            canvas = Image.new("RGB", (canvas_w, canvas_h), color=top_fill)
            draw = ImageDraw.Draw(canvas)
            for y in range(canvas_h):
                t = y / max(1, canvas_h - 1)
                row = (
                    int(top_fill[0] * (1 - t) + bottom_fill[0] * t),
                    int(top_fill[1] * (1 - t) + bottom_fill[1] * t),
                    int(top_fill[2] * (1 - t) + bottom_fill[2] * t),
                )
                draw.line((0, y, canvas_w, y), fill=row)

            canvas.paste(src, (0, top_margin))
            divider_color = tuple(max(0, int(v * 0.72)) for v in mix)
            draw.line((0, top_margin, canvas_w, top_margin), fill=divider_color, width=max(1, int(canvas_w * 0.002)))
            draw.line(
                (0, top_margin + src_h, canvas_w, top_margin + src_h),
                fill=divider_color,
                width=max(1, int(canvas_w * 0.002)),
            )

            pad = max(12, int(canvas_w * 0.03))
            top_band_h = max(28, top_margin - pad * 2)
            bottom_band_h = max(56, bottom_margin - pad * 2)
            logo_w = max(120, int(canvas_w * 0.24))
            logo_h = max(42, int(top_band_h * 0.72))
            qr_size = max(96, min(int(bottom_band_h * 0.72), int(canvas_w * 0.24)))
            hotline_h = max(28, int(bottom_band_h * 0.26))
            hotline_w = max(160, int(canvas_w * 0.30))
            gap = max(12, int(canvas_w * 0.02))

            meta = {
                "layout_mode": layout_mode,
                "core_rect": [0, top_margin, src_w, src_h],
                "logo_safe_rects": {
                    "top_left": [pad, pad, logo_w, logo_h],
                    "top_right": [canvas_w - pad - logo_w, pad, logo_w, logo_h],
                    "bottom_left": [pad, top_margin + src_h + pad, logo_w, logo_h],
                    "bottom_right": [canvas_w - pad - logo_w, top_margin + src_h + pad, logo_w, logo_h],
                },
                "qr_safe_rects": {
                    "bottom_left": [pad, canvas_h - pad - qr_size, qr_size, qr_size],
                    "bottom_right": [canvas_w - pad - qr_size, canvas_h - pad - qr_size, qr_size, qr_size],
                },
                "hotline_safe_rects": {
                    "bottom_left": [pad + qr_size + gap, canvas_h - pad - hotline_h, hotline_w, hotline_h],
                    "bottom_right": [canvas_w - pad - qr_size - gap - hotline_w, canvas_h - pad - hotline_h, hotline_w, hotline_h],
                },
            }

            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            out_path = GENERATED_DIR / f"postprocess_ai_canvas_{uuid.uuid4().hex}.png"
            canvas.save(out_path, format="PNG", optimize=True)
            canvas.close()
            return out_path, meta
        finally:
            src.close()

    @staticmethod
    def _restore_protected_core(ai_result_path: Path, protected_canvas_path: Path, meta: dict) -> Path:
        ai_image = Image.open(ai_result_path).convert("RGBA")
        protected = Image.open(protected_canvas_path).convert("RGBA")
        try:
            if ai_image.size != protected.size:
                ai_image = ai_image.resize(protected.size, Image.Resampling.LANCZOS)

            core = meta.get("core_rect") or [0, 0, protected.width, protected.height]
            x, y, w, h = int(core[0]), int(core[1]), int(core[2]), int(core[3])
            x = max(0, min(protected.width - 1, x))
            y = max(0, min(protected.height - 1, y))
            w = max(1, min(protected.width - x, w))
            h = max(1, min(protected.height - y, h))

            protected_crop = protected.crop((x, y, x + w, y + h))
            ai_image.paste(protected_crop, (x, y))
            protected_crop.close()

            out_path = GENERATED_DIR / f"postprocess_ai_locked_{uuid.uuid4().hex}.png"
            ai_image.convert("RGB").save(out_path, format="PNG", optimize=True)
            return out_path
        finally:
            ai_image.close()
            protected.close()

    @staticmethod
    def _build_ai_brand_prompt(req: PostprocessImageRequest, *, has_logo: bool, has_qr: bool, layout_mode: str) -> str:
        logo_clause = (
            f"Use provided logo and place exactly one at {PostprocessService._LOGO_POSITION_EN.get(req.logo_position, 'top-right')}."
            if has_logo
            else "No logo image is provided; reserve a clean logo placeholder area."
        )
        qr_clause = (
            f"Reserve QR zone at {req.qr_position.replace('_', '-')} area."
            if has_qr
            else "Do not add QR code if not provided."
        )
        title = req.ai_title_text or "【轻享新生活】·你的夏日新宠"
        cta = req.ai_cta_text or "扫码即刻体验，开启新篇章！"

        protocol = (
            "Brand Integration Poster Protocol:\n"
            f"- Input layout mode: {layout_mode}.\n"
            "- Preserve the original core image content strictly: character identity, scene objects, panel structure, all Chinese dialogue text.\n"
            "- DO NOT alter core storytelling frames, composition, or speech bubble text.\n"
            "- Only edit branding zones (top and bottom bands) with commercial layout quality.\n"
            f"- Target headline (for local render only): {title}\n"
            f"- Target CTA (for local render only): {cta}\n"
            f"- {logo_clause}\n"
            f"- {qr_clause}\n"
            f"- Target hotline text (for local render only): {req.phone_number or 'placeholder'}.\n"
            "- IMPORTANT: do NOT generate any new readable text, numbers, QR patterns, or logos in the image.\n"
            "- Leave clean readable spaces for local text rendering in top and bottom branding zones.\n"
            "- Style: elegant, soft, watercolor-retro consistency with ambient occlusion and subtle highlight/reflection.\n"
            "- Avoid: hard cut stickers,乱码, irrelevant watermarks/icons, duplicated logos."
        )
        user_prompt = req.ai_prompt.strip()
        if user_prompt:
            return f"{user_prompt}\n\n{protocol}"
        return protocol

    @staticmethod
    def _fit_text_in_rect(
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        max_w: int,
        max_h: int,
        max_size: int,
        min_size: int = 14,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for size in range(max_size, min_size - 1, -2):
            font = PostprocessService._load_font(size)
            box = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, size // 16))
            w = max(1, box[2] - box[0])
            h = max(1, box[3] - box[1])
            if w <= max_w and h <= max_h:
                return font
        return PostprocessService._load_font(min_size)

    @staticmethod
    def _draw_text_in_rect(
        image: Image.Image,
        *,
        rect: tuple[int, int, int, int],
        text: str,
        color: tuple[int, int, int, int],
        stroke_color: tuple[int, int, int, int],
    ) -> None:
        if not text.strip():
            return
        x, y, w, h = rect
        if w <= 4 or h <= 4:
            return
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        font = PostprocessService._fit_text_in_rect(
            draw,
            text,
            max_w=max(1, w - 8),
            max_h=max(1, h - 8),
            max_size=max(18, int(h * 0.62)),
            min_size=14,
        )
        box = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, font.size // 16))
        tw = max(1, box[2] - box[0])
        th = max(1, box[3] - box[1])
        tx = x + max(0, (w - tw) // 2)
        ty = y + max(0, (h - th) // 2)
        draw.text(
            (tx, ty),
            text,
            font=font,
            fill=color,
            stroke_width=max(1, font.size // 16),
            stroke_fill=stroke_color,
        )
        image.alpha_composite(layer)

    @staticmethod
    def _draw_ai_brand_texts(
        image: Image.Image,
        *,
        req: PostprocessImageRequest,
        layout_meta: dict,
        has_qr: bool,
    ) -> None:
        title_text = (req.ai_title_text or "【轻享新生活】·你的夏日新宠").strip()
        cta_text = (req.ai_cta_text or "扫码即刻体验，开启新篇章！").strip()
        hotline = req.phone_number.strip()

        core = layout_meta.get("core_rect") or [0, 0, image.width, image.height]
        try:
            core_x, core_y, core_w, core_h = (int(core[0]), int(core[1]), int(core[2]), int(core[3]))
        except (TypeError, ValueError):
            core_x, core_y, core_w, core_h = 0, 0, image.width, image.height

        pad = max(12, int(image.width * 0.03))
        title_rect = (pad, pad, max(1, image.width - pad * 2), max(24, core_y - pad * 2))
        bottom_band_top = core_y + core_h
        cta_height = max(30, int((image.height - bottom_band_top) * 0.35))
        cta_rect = (pad, bottom_band_top + pad, max(1, image.width - pad * 2), max(24, cta_height - pad))

        text_color = (28, 28, 28, 240)
        text_stroke = (255, 255, 255, 215)
        PostprocessService._draw_text_in_rect(
            image,
            rect=title_rect,
            text=title_text,
            color=text_color,
            stroke_color=text_stroke,
        )
        PostprocessService._draw_text_in_rect(
            image,
            rect=cta_rect,
            text=cta_text,
            color=text_color,
            stroke_color=text_stroke,
        )

        if has_qr or not hotline:
            return

        hotline_rects = layout_meta.get("hotline_safe_rects")
        if isinstance(hotline_rects, dict):
            raw = hotline_rects.get(req.qr_position) or hotline_rects.get("bottom_right")
            if isinstance(raw, list) and len(raw) == 4:
                hx, hy, hw, hh = (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
                PostprocessService._draw_text_in_rect(
                    image,
                    rect=(hx, hy, hw, hh),
                    text=f"热线号码 {hotline}",
                    color=text_color,
                    stroke_color=text_stroke,
                )

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
        qr_file: Optional[Path],
    ) -> str:
        prepared_canvas_path, layout_meta = PostprocessService._build_ai_brand_canvas(source_path, req)
        prepared = Image.open(prepared_canvas_path).convert("RGBA")
        try:
            if logo_file:
                PostprocessService._apply_logo(
                    prepared,
                    logo_file,
                    position=req.logo_position,
                    scale=req.logo_scale,
                    opacity=req.logo_opacity,
                )
            if qr_file and req.qr_enabled:
                PostprocessService._apply_qr_phone_card(
                    prepared,
                    qr_file,
                    position=req.qr_position,
                    scale=req.qr_scale,
                    phone_number=req.phone_number,
                    card_opacity=req.qr_card_opacity,
                )
            prepared.convert("RGB").save(prepared_canvas_path, format="PNG", optimize=True)
        finally:
            prepared.close()

        references = [PostprocessService._path_to_data_url_limited(prepared_canvas_path)]
        if logo_file:
            references.append(PostprocessService._path_to_data_url_limited(logo_file))
        if qr_file:
            references.append(PostprocessService._path_to_data_url_limited(qr_file))

        prompt = PostprocessService._build_ai_brand_prompt(
            req,
            has_logo=bool(logo_file),
            has_qr=bool(qr_file and req.qr_enabled),
            layout_mode=str(layout_meta.get("layout_mode") or "single"),
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
            compressed_refs = [PostprocessService._path_to_data_url_limited(prepared_canvas_path)]
            if logo_file:
                compressed_refs.append(PostprocessService._path_to_data_url_limited(logo_file))
            if qr_file:
                compressed_refs.append(PostprocessService._path_to_data_url_limited(qr_file))

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
        locked_path = PostprocessService._restore_protected_core(
            ai_result_path=local_path,
            protected_canvas_path=prepared_canvas_path,
            meta=layout_meta,
        )
        final_image = Image.open(locked_path).convert("RGBA")
        try:
            PostprocessService._draw_ai_brand_texts(
                final_image,
                req=req,
                layout_meta=layout_meta,
                has_qr=bool(qr_file and req.qr_enabled),
            )
            out_path = GENERATED_DIR / f"postprocess_ai_texted_{uuid.uuid4().hex}.png"
            final_image.convert("RGB").save(out_path, format="PNG", optimize=True)
        finally:
            final_image.close()
        return f"/static/generated/{out_path.name}"

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
                        qr_file=qr_file,
                    )
                    if qr_file:
                        ai_image_path = PostprocessService._resolve_source_path(saved_path)
                        ai_image = Image.open(ai_image_path).convert("RGBA")
                        try:
                            PostprocessService._apply_qr_phone_card(
                                ai_image,
                                qr_file,
                                position=req.qr_position,
                                scale=req.qr_scale,
                                phone_number=req.phone_number,
                                card_opacity=req.qr_card_opacity,
                            )
                            out_name = f"postprocessed_ai_{uuid.uuid4().hex}.png"
                            out_path = GENERATED_DIR / out_name
                            ai_image.convert("RGB").save(out_path, format="PNG", optimize=True)
                            saved_path = f"/static/generated/{out_name}"
                        finally:
                            ai_image.close()
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
