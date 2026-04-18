from __future__ import annotations

import base64
import inspect
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont

from ..poster_config import ASPECT_RATIOS
from ..prompt_engineering import build_comic_panel_prompt, build_comic_storyboard
from ..schemas import GenerateComicRequest
from .comic_prompt_service import ComicPromptService
from .image_provider import ImageProviderService
from .storage import StorageService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"


def _path_to_data_url(local_path: Path) -> str:
    data = base64.b64encode(local_path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{data}"


async def _download_to_local(image_url: str) -> Path:
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.get(image_url)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"download panel image failed: status={resp.status_code}")
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

    raise HTTPException(status_code=502, detail="cannot locate generated panel image file")


def _resolve_product_reference_data_url(upload_dir: Path, product_image_id: Optional[str]) -> Optional[str]:
    if not product_image_id:
        return None
    matches = list(upload_dir.glob(f"{product_image_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="product_image_id invalid or file missing")
    data_url = StorageService.file_to_data_url(matches[0].name)
    if not data_url:
        raise HTTPException(status_code=404, detail="product image file not found")
    return data_url


def _pick_cjk_font(font_size: int) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), font_size)
            except OSError:
                continue
    return ImageFont.load_default()


def _char_units(ch: str) -> int:
    # ASCII counts as 1, CJK counts as 2 for rough wrap control.
    return 1 if ord(ch) < 128 else 2


def _wrap_text_for_width(text: str, max_units: int) -> list[str]:
    lines: list[str] = []
    current = ""
    units = 0
    for ch in text:
        if ch == "\n":
            lines.append(current.strip())
            current = ""
            units = 0
            continue
        ch_units = _char_units(ch)
        if units + ch_units > max_units and current:
            lines.append(current.strip())
            current = ch
            units = ch_units
        else:
            current += ch
            units += ch_units
    if current.strip():
        lines.append(current.strip())
    return lines


def _append_panel_caption(raw_panel_path: Path, panel_index: int, dialogue: str) -> Path:
    image = Image.open(raw_panel_path).convert("RGB")
    width, height = image.size
    caption_height = max(84, int(height * 0.16))
    canvas = Image.new("RGB", (width, height + caption_height), color=(255, 255, 255))
    canvas.paste(image, (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.line([(0, height), (width, height)], fill=(220, 220, 220), width=2)

    font_size = max(18, int(caption_height * 0.34))
    font = _pick_cjk_font(font_size=font_size)
    text = f"第{panel_index}格：{dialogue.strip() if dialogue.strip() else '（无对白）'}"
    lines = _wrap_text_for_width(text, max_units=36)[:2]

    y = height + 10
    for line in lines:
        draw.text((14, y), line, fill=(35, 35, 35), font=font)
        y += font_size + 4

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_DIR / f"comic_panel_caption_{uuid.uuid4().hex}.png"
    canvas.save(out, format="PNG", optimize=True)
    return out


def _dialogue_rule(language: str, text_mode: str) -> str:
    if text_mode == "post_render":
        return "画面中不要渲染任何可读文字，只保留空白对话气泡区域。"
    if language == "zh-CN":
        return "对话气泡文字必须为简体中文，禁止出现英文。"
    return "All speech bubble text must be in English."


def _apply_reference_only_guard(
    *,
    prompt: str,
    panel_index: int,
    panel_count: int,
    language: str,
    text_mode: str,
    ratio_label: str,
    ratio_size: str,
) -> str:
    language_text = "简体中文" if language == "zh-CN" else "English"
    guard = f"""
【连续性参考图规则】
- 第 {panel_index}/{panel_count} 格：若提供上一格参考图，仅用于保持角色、产品、服装道具与世界观一致性。
- 必须生成新的构图、机位、动作、镜头距离和光影关系，禁止复刻上一格布局或姿势。
- 禁止复制上一格噪点、压缩伪影、污渍纹理和边缘瑕疵，画面应干净清晰。
- 与上一格相比必须有明确叙事推进，不可做重复画面。

【语言】{language_text}
【文字策略】{_dialogue_rule(language=language, text_mode=text_mode)}

【比例】{ratio_label}（{ratio_size}）
【硬性限制】
- 禁止水印、乱码、无关 logo
- 禁止写实摄影风格
""".strip()
    return f"{prompt.strip()}\n\n{guard}"


async def _emit_progress(
    progress_hook: Optional[Callable[[dict], Awaitable[None] | None]],
    payload: dict,
) -> None:
    if not progress_hook:
        return
    maybe = progress_hook(payload)
    if inspect.isawaitable(maybe):
        await maybe


def compose_comic_strip(panel_paths: list[Path], panel_count: int) -> str:
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
    async def generate_comic(
        req: GenerateComicRequest,
        upload_dir: Path,
        progress_hook: Optional[Callable[[dict], Awaitable[None] | None]] = None,
    ) -> dict:
        ratio = ASPECT_RATIOS.get(req.ratio_key, ASPECT_RATIOS["square"])
        product_description = (req.product_description or "").strip()
        character_hint = (req.character_description or "").strip()
        language = req.language
        text_mode = req.text_mode

        storyboard = build_comic_storyboard(
            panel_count=req.panel_count,
            product_name=req.product_name,
            product_description=product_description,
        )
        llm_panels = await ComicPromptService.generate_panel_prompts(
            api_key=req.api_key,
            base_url=req.base_url,
            panel_count=req.panel_count,
            product_name=req.product_name,
            product_description=product_description,
            character_hint=character_hint,
            style=req.style,
            language=language,
            text_mode=text_mode,
            ratio_label=ratio["label"],
            ratio_size=ratio["size"],
            storyboard=storyboard,
        )
        llm_panel_map = {panel["index"]: panel for panel in llm_panels}
        product_reference_data_url = _resolve_product_reference_data_url(upload_dir, req.product_image_id)

        panels = []
        last_panel_data_url: Optional[str] = None
        local_paths: list[Path] = []

        for beat in storyboard:
            panel_index = beat["index"]
            llm_panel = llm_panel_map.get(panel_index, {})
            scene = llm_panel.get("scene") or beat["scene"]
            camera = llm_panel.get("camera") or beat["camera"]
            action = llm_panel.get("action") or beat["action"]
            emotion = llm_panel.get("emotion") or beat["emotion"]
            dialogue = llm_panel.get("dialogue") or beat["dialogue"]
            continuity_note = llm_panel.get("continuity_note") or beat["continuity_note"]

            fallback_prompt = build_comic_panel_prompt(
                panel_index=panel_index,
                panel_count=req.panel_count,
                product_name=req.product_name,
                product_description=product_description,
                scene_description=scene,
                style=req.style,
                character_hint=character_hint,
                camera=camera,
                action=action,
                emotion=emotion,
                dialogue=dialogue,
                continuity_note=continuity_note,
                language=language,
                text_mode=text_mode,
                ratio_label=ratio["label"],
                ratio_size=ratio["size"],
            )
            prompt = llm_panel.get("prompt") or fallback_prompt
            prompt = _apply_reference_only_guard(
                prompt=prompt,
                panel_index=panel_index,
                panel_count=req.panel_count,
                language=language,
                text_mode=text_mode,
                ratio_label=ratio["label"],
                ratio_size=ratio["size"],
            )

            reference_images: list[str] = []
            if product_reference_data_url:
                reference_images.append(product_reference_data_url)
            if last_panel_data_url and last_panel_data_url not in reference_images:
                reference_images.append(last_panel_data_url)

            scene_summary = f"{scene} | {action}"
            await _emit_progress(
                progress_hook,
                {
                    "type": "panel_prompt",
                    "panel": {
                        "index": panel_index,
                        "scene": scene_summary,
                        "prompt": prompt,
                    },
                },
            )
            try:
                image = await ImageProviderService.generate_image(
                    api_key=req.api_key,
                    base_url=req.base_url,
                    model=req.model,
                    prompt=prompt,
                    ratio_key=req.ratio_key,
                    logo_base64_data_url=None,
                    reference_images_data_urls=reference_images or None,
                )
                raw_local_path = await _ensure_local_path(image)
                last_panel_data_url = _path_to_data_url(raw_local_path)

                display_path = raw_local_path
                if text_mode == "post_render" and language == "zh-CN":
                    display_path = _append_panel_caption(
                        raw_panel_path=raw_local_path,
                        panel_index=panel_index,
                        dialogue=dialogue,
                    )

                local_paths.append(display_path)

                panel_result = {
                    "index": panel_index,
                    "scene": scene_summary,
                    "prompt": prompt,
                    "saved_path": f"/static/generated/{display_path.name}",
                    "error": None,
                }
                panels.append(panel_result)
                await _emit_progress(progress_hook, {"type": "panel_done", "panel": panel_result})
            except Exception as exc:  # noqa: BLE001
                panel_result = {
                    "index": panel_index,
                    "scene": scene_summary,
                    "prompt": prompt,
                    "error": str(exc),
                }
                panels.append(panel_result)
                await _emit_progress(progress_hook, {"type": "panel_error", "panel": panel_result})

        composite_path: Optional[str] = None
        if local_paths:
            composite_path = compose_comic_strip(local_paths, req.panel_count)

        return {
            "panel_count": req.panel_count,
            "panels": panels,
            "composite_path": composite_path,
        }
