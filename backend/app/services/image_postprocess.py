from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"


def _region_brightness(image: Image.Image, x: int, y: int, w: int, h: int) -> float:
    """返回指定区域的平均亮度（0=纯黑, 255=纯白）。"""
    region = image.crop((x, y, min(x + w, image.width), min(y + h, image.height))).convert("L")
    return ImageStat.Stat(region).mean[0]


def add_logo_to_image(image_path: str, logo_path: str, position: str) -> str:
    """
    固定模式 Logo 后处理：
    - Logo 最大边 <= 海报对应边 20%
    - 支持四角位置
    - 自适应背景框：检测落点亮度，暗背景加白框，亮背景加深色框
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    base = Image.open(image_path).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    base_w, base_h = base.size
    logo_w, logo_h = logo.size

    max_logo_w = int(base_w * 0.20)
    max_logo_h = int(base_h * 0.20)
    scale = min(max_logo_w / logo_w, max_logo_h / logo_h, 1.0)

    scaled_w = max(1, int(logo_w * scale))
    scaled_h = max(1, int(logo_h * scale))
    resized_logo = logo.resize((scaled_w, scaled_h), Image.LANCZOS)

    padding = max(int(min(base_w, base_h) * 0.03), 8)

    if position == "top_left":
        x, y = padding, padding
    elif position == "top_right":
        x, y = base_w - scaled_w - padding, padding
    elif position == "bottom_left":
        x, y = padding, base_h - scaled_h - padding
    else:  # bottom_right
        x, y = base_w - scaled_w - padding, base_h - scaled_h - padding

    # 自适应背景框
    brightness = _region_brightness(base, x, y, scaled_w, scaled_h)
    fp = max(10, int(min(scaled_w, scaled_h) * 0.25))
    frame_fill = (255, 255, 255, 160) if brightness < 128 else (30, 30, 30, 140)

    frame_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(frame_layer).rounded_rectangle(
        [x - fp, y - fp, x + scaled_w + fp, y + scaled_h + fp],
        radius=fp,
        fill=frame_fill,
    )

    composed = base.copy()
    composed.alpha_composite(frame_layer)
    composed.alpha_composite(resized_logo, (x, y))

    out_name = f"generated_fixed_logo_{uuid.uuid4().hex}.png"
    out_path = GENERATED_DIR / out_name
    composed.convert("RGB").save(out_path, format="PNG", optimize=True)
    return str(out_path)
