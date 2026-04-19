from __future__ import annotations

import json
import re
from typing import Optional, Sequence

import httpx

from ..poster_config import STYLE_MAP


class ComicPromptService:
    PROMPT_MODEL = "qwen3.6-plus"
    FALLBACK_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        value = (base_url or "").strip().rstrip("/")
        if not value:
            return ComicPromptService.FALLBACK_BASE_URL
        return value

    @staticmethod
    def _extract_text_content(payload: dict) -> Optional[str]:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message", {}) if isinstance(first, dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                if parts:
                    return "\n".join(parts)

        output = payload.get("output")
        if isinstance(output, dict):
            output_choices = output.get("choices")
            if isinstance(output_choices, list) and output_choices:
                first = output_choices[0] if isinstance(output_choices[0], dict) else {}
                message = first.get("message", {}) if isinstance(first, dict) else {}
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                    if parts:
                        return "\n".join(parts)
        return None

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        stripped = text.strip()
        match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return stripped

    @staticmethod
    def _load_json_object(text: str) -> Optional[dict]:
        cleaned = ComicPromptService._strip_code_fence(text)
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                data = json.loads(cleaned[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _dialogue_rule(language: str, text_mode: str) -> str:
        if text_mode == "post_render":
            return "画面中不要渲染任何可读文字，只保留空白对话气泡区域。"
        if language == "zh-CN":
            return "对话气泡文字必须为简体中文，禁止出现英文。"
        return "All speech bubble text must be in English."

    @staticmethod
    def _language_text(language: str) -> str:
        return "简体中文" if language == "zh-CN" else "English"

    @staticmethod
    def _normalize_panel_items(data: dict, panel_count: int) -> list[dict]:
        panels = data.get("panels")
        if not isinstance(panels, list):
            return []

        normalized: list[dict] = []
        for i, raw in enumerate(panels, start=1):
            if not isinstance(raw, dict):
                continue
            index_raw = raw.get("index", i)
            try:
                index = int(index_raw)
            except (TypeError, ValueError):
                index = i
            if index < 1 or index > panel_count:
                continue

            panel = {
                "index": index,
                "scene": str(raw.get("scene", "")).strip(),
                "camera": str(raw.get("camera", "")).strip(),
                "action": str(raw.get("action", "")).strip(),
                "emotion": str(raw.get("emotion", "")).strip(),
                "dialogue": str(raw.get("dialogue", "")).strip(),
                "continuity_note": str(raw.get("continuity_note", "")).strip(),
                "prompt": str(raw.get("prompt", "")).strip(),
            }
            if panel["prompt"]:
                normalized.append(panel)

        normalized.sort(key=lambda x: x["index"])
        return normalized

    @staticmethod
    async def generate_panel_prompts(
        *,
        api_key: str,
        base_url: str,
        panel_count: int,
        product_name: str,
        product_description: str,
        character_hint: str,
        style: str,
        language: str,
        text_mode: str,
        ratio_label: str,
        ratio_size: str,
        storyboard: Sequence[dict],
    ) -> list[dict]:
        normalized_base_url = ComicPromptService._normalize_base_url(base_url)
        endpoint = f"{normalized_base_url}/chat/completions"

        style_desc = STYLE_MAP.get(style, {}).get("prompt_description", style)
        storyboard_json = json.dumps(list(storyboard), ensure_ascii=False)
        language_text = ComicPromptService._language_text(language)
        dialogue_rule = ComicPromptService._dialogue_rule(language=language, text_mode=text_mode)
        characters = character_hint.strip() if character_hint.strip() else "1-2位角色（人物或拟人均可）"
        product_desc = product_description.strip() if product_description.strip() else "未提供补充描述"

        system_prompt = """
你是“电商漫画分镜编剧 + 图像提示词工程师”。
请根据输入生成逐格漫画图像提示词，要求故事连贯、每格推进明显。

核心要求：
1. 角色与产品必须在全篇保持一致（外观、服装、道具、产品结构）。
2. 每一格都要有新的叙事信息，禁止重复同姿势、同机位、同构图。
3. 若有上一格参考图，它只能用于一致性校准，绝不能复刻上一格布局、动作和噪点纹理。
4. 输出用于图像模型，描述要具体可执行，避免空泛词。
5. 必须返回严格 JSON，不要返回 Markdown、解释性文字或代码块。
6. `dialogue` 必须由你结合当前分镜的 action/emotion 现场原创，不得照抄草案中的提示语。

输出 JSON 格式：
{
  "panels": [
    {
      "index": 1,
      "scene": "本格主题",
      "camera": "镜头语言",
      "action": "动作描述",
      "emotion": "情绪描述",
      "dialogue": "本格对白",
      "continuity_note": "与上一格衔接说明",
      "prompt": "给图像模型的最终提示词"
    }
  ]
}
""".strip()

        user_prompt = f"""
请生成 {panel_count} 格漫画提示词。

【语言】{language_text}
【文字策略】{dialogue_rule}
【产品】{product_name}
【产品描述】{product_desc}
【角色设定】{characters}
【风格】{style_desc}
【比例】{ratio_label}（{ratio_size}）

【分镜草案（必须遵循并强化故事推进）】
{storyboard_json}

请确保每个 panel 的 `prompt` 中都明确体现：
- 这是第 index/{panel_count} 格；
- 与上一格相比必须有构图或动作推进；
- 如果提供上一格参考图，仅作一致性参考，禁止复刻画面和噪点。
- 每格 `dialogue` 都要原创，语气贴合该格情绪，不得使用固定模板句。
- 若草案中出现 `dialogue_hint`，仅作方向参考，不能原样复述。
""".strip()

        request_json = {
            "model": ComicPromptService.PROMPT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(endpoint, headers=headers, json=request_json)
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        try:
            payload = response.json()
        except ValueError:
            return []

        content = ComicPromptService._extract_text_content(payload)
        if not content:
            return []

        data = ComicPromptService._load_json_object(content)
        if not data:
            return []

        return ComicPromptService._normalize_panel_items(data=data, panel_count=panel_count)
