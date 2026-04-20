from __future__ import annotations

import base64
import inspect
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx
from fastapi import HTTPException
from PIL import Image

from ..poster_config import ASPECT_RATIOS
from ..prompt_engineering import build_comic_panel_prompt, build_comic_storyboard
from ..schemas import GenerateComicRequest
from .comic_prompt_service import ComicPromptService
from .image_provider import ImageProviderService
from .storage import StorageService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"
COMIC_COMPOSITE_LAYOUTS = {
    4: {"mobile": (2, 2), "landscape": (4, 1)},
    6: {"mobile": (2, 3), "landscape": (3, 2)},
}
COMIC_COMPOSITE_CANVAS_SIZES = {
    "mobile": (1800, 3200),  # 9:16
    "landscape": (3200, 1800),  # 16:9
}


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


def _dialogue_rule(language: str, text_mode: str) -> str:
    if text_mode == "post_render":
        return "画面中不要渲染任何可读文字，只保留空白对话气泡区域。"
    if language == "zh-CN":
        return "对话气泡文字必须为简体中文，禁止出现英文。"
    return "All speech bubble text must be in English."


def _fallback_dialogue(language: str) -> str:
    return "这就搞定" if language == "zh-CN" else "Done, this works."


def _normalize_dialogue(dialogue: str, max_chars: int = 20) -> str:
    value = " ".join((dialogue or "").split()).strip().strip("\"'“”‘’")
    if len(value) > max_chars:
        return value[:max_chars].rstrip()
    return value


def _compose_generation_prompt(
    *,
    visual_prompt: str,
    dialogue: str,
    emotion: str,
    product_focus: str,
    text_mode: str,
) -> str:
    visual = visual_prompt.strip()
    if not visual:
        return ""

    spoken = _normalize_dialogue(dialogue)
    emotion_text = (emotion or "focused").strip()
    focus_text = (product_focus or "").strip()

    if text_mode == "post_render":
        bubble_text = "speech bubble area left blank (no readable text)"
    else:
        bubble_line = spoken or "Ready."
        bubble_text = f'speech bubble with text \"{bubble_line}\"'

    parts = [
        visual,
        "comic style",
        bubble_text,
        f"emotion: {emotion_text}",
        f"highlight product: {focus_text}" if focus_text else "highlight product",
    ]
    return ", ".join(parts)


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


def _resize_contain(panel: Image.Image, box_w: int, box_h: int, *, resample: int) -> Image.Image:
    src_w, src_h = panel.size
    scale = min(box_w / src_w, box_h / src_h)
    out_w = max(1, int(src_w * scale))
    out_h = max(1, int(src_h * scale))
    return panel.resize((out_w, out_h), resample=resample)


def compose_comic_strip(panel_paths: list[Path], panel_count: int, composite_ratio_key: str) -> str:
    if not panel_paths:
        raise HTTPException(status_code=500, detail="no panel images to compose")

    layout_map = COMIC_COMPOSITE_LAYOUTS.get(panel_count)
    if not layout_map:
        raise HTTPException(status_code=500, detail=f"unsupported panel_count for composite: {panel_count}")

    ratio_key = composite_ratio_key if composite_ratio_key in COMIC_COMPOSITE_CANVAS_SIZES else "mobile"
    cols, rows = layout_map[ratio_key]
    canvas_w, canvas_h = COMIC_COMPOSITE_CANVAS_SIZES[ratio_key]
    outer_padding = max(24, int(min(canvas_w, canvas_h) * 0.025))
    gutter = max(14, int(outer_padding * 0.6))
    usable_w = canvas_w - (outer_padding * 2) - (gutter * (cols - 1))
    usable_h = canvas_h - (outer_padding * 2) - (gutter * (rows - 1))
    cell_w = usable_w // cols
    cell_h = usable_h // rows

    if cell_w <= 0 or cell_h <= 0:
        raise HTTPException(status_code=500, detail="invalid composite layout size")

    resample = getattr(Image, "Resampling", Image).LANCZOS
    panels = [Image.open(p).convert("RGB") for p in panel_paths]
    try:
        composite = Image.new("RGB", (canvas_w, canvas_h), color=(255, 255, 255))
        for i, panel in enumerate(panels):
            row = i // cols
            col = i % cols
            if row >= rows:
                break

            cell_x = outer_padding + (col * (cell_w + gutter))
            cell_y = outer_padding + (row * (cell_h + gutter))
            fitted = _resize_contain(panel, cell_w, cell_h, resample=resample)
            paste_x = cell_x + (cell_w - fitted.width) // 2
            paste_y = cell_y + (cell_h - fitted.height) // 2
            composite.paste(fitted, (paste_x, paste_y))
            fitted.close()

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        out_name = f"comic_strip_{uuid.uuid4().hex}.png"
        out_path = GENERATED_DIR / out_name
        composite.save(out_path, format="PNG", optimize=True)
    finally:
        for panel in panels:
            panel.close()

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
            scene = beat["scene"]
            camera = beat["camera"]
            action = beat["action"]
            emotion = (llm_panel.get("emotion") or beat["emotion"]).strip()
            dialogue = _normalize_dialogue(llm_panel.get("dialogue") or "")
            if not dialogue:
                dialogue = _fallback_dialogue(language)
            product_focus = (llm_panel.get("product_focus") or req.product_name).strip()
            visual_prompt = (llm_panel.get("visual_prompt") or "").strip()
            continuity_note = beat["continuity_note"]
            scene_description = visual_prompt or f"{scene}; {camera}; {action}"

            fallback_prompt = build_comic_panel_prompt(
                panel_index=panel_index,
                panel_count=req.panel_count,
                product_name=req.product_name,
                product_description=product_description,
                scene_description=scene_description,
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
            structured_prompt = _compose_generation_prompt(
                visual_prompt=visual_prompt,
                dialogue=dialogue,
                emotion=emotion,
                product_focus=product_focus,
                text_mode=text_mode,
            )
            prompt = structured_prompt or fallback_prompt
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
        if len(local_paths) == req.panel_count:
            composite_path = compose_comic_strip(local_paths, req.panel_count, req.composite_ratio_key)

        return {
            "panel_count": req.panel_count,
            "panels": panels,
            "composite_path": composite_path,
        }
