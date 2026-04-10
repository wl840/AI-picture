from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"


def add_logo_to_image(image_path: str, logo_path: str, position: str) -> str:
    """
    固定模式 Logo 后处理：
    - 使用 Pillow 贴图
    - Logo 最大边 <= 海报对应边 20%
    - 支持四角位置
    - 保留透明通道
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    base = Image.open(image_path).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    base_w, base_h = base.size
    logo_w, logo_h = logo.size

    # 控制最大占比（<=20%），并按比例缩放避免变形
    max_logo_w = int(base_w * 0.20)
    max_logo_h = int(base_h * 0.20)
    scale = min(max_logo_w / logo_w, max_logo_h / logo_h, 1.0)

    scaled_w = max(1, int(logo_w * scale))
    scaled_h = max(1, int(logo_h * scale))
    resized_logo = logo.resize((scaled_w, scaled_h), Image.LANCZOS)

    # 内边距，避免贴边
    padding = max(int(min(base_w, base_h) * 0.03), 8)

    if position == "top_left":
        x, y = padding, padding
    elif position == "top_right":
        x, y = base_w - scaled_w - padding, padding
    elif position == "bottom_left":
        x, y = padding, base_h - scaled_h - padding
    else:  # bottom_right
        x, y = base_w - scaled_w - padding, base_h - scaled_h - padding

    composed = base.copy()
    composed.alpha_composite(resized_logo, (x, y))

    out_name = f"generated_fixed_logo_{uuid.uuid4().hex}.png"
    out_path = GENERATED_DIR / out_name
    composed.convert("RGB").save(out_path, format="PNG", optimize=True)
    return str(out_path)
