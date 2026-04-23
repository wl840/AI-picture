from __future__ import annotations

import json
import re
from typing import Optional, Sequence

import httpx

from ..poster_config import STYLE_MAP


class ComicPromptService:
    PROMPT_MODEL = "gpt-5.4"
    DIALOGUE_POLISH_MODEL = "gpt-5.4"
    FALLBACK_BASE_URL = "https://api.psydo.top/v1"
    MAX_DIALOGUE_CHARS = 20
    MAX_RETRIES = 1

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
                    parts = []
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
    def _compact_text(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @staticmethod
    def _normalize_dialogue(value: str, max_chars: int) -> str:
        normalized = ComicPromptService._compact_text(value).strip("\"'“”‘’")
        if len(normalized) > max_chars:
            normalized = normalized[:max_chars].rstrip()
        return normalized

    @staticmethod
    def _language_text(language: str) -> str:
        return "Simplified Chinese" if language == "zh-CN" else "English"

    @staticmethod
    def _build_system_prompt() -> str:
        return (
            "You are an advertising comic storyboard generator.\n"
            "Return strict JSON only. Never output markdown.\n"
            "Every panel must use this schema:\n"
            "{"
            '"index": 1, '
            '"visual_prompt": "string", '
            '"dialogue": "string", '
            '"emotion": "string", '
            '"product_focus": "string"'
            "}.\n"
            "Rules:\n"
            "1) dialogue must sound like a human speaking in a comic scene.\n"
            "2) dialogue must mention or imply the product selling point.\n"
            "3) dialogue must strongly match the visual action.\n"
            "4) dialogue max 20 characters.\n"
            "5) visual_prompt must be drawable: include character, action, and scene.\n"
            "6) Keep style continuity across panels.\n"
            "7) Each panel must have a clearly different camera framing or action from the previous panel.\n"
            "8) Never output split-screen, collage, before-after side-by-side, or half-frame comparison.\n"
            "9) Never output a hard vertical or horizontal lighting split through the frame.\n"
            "10) Panel 4 must be a single-shot continuation of panel 3, not a comparison collage.\n"
            "11) Preserve one character identity and one world continuity across panels.\n"
            "12) No duplicated character clones in the same panel."
        )

    @staticmethod
    def _build_user_prompt(
        *,
        panel_count: int,
        product_name: str,
        product_description: str,
        character_hint: str,
        style_desc: str,
        language_text: str,
        ratio_label: str,
        ratio_size: str,
        storyboard_json: str,
    ) -> str:
        characters = character_hint.strip() if character_hint.strip() else "1-2 recurring characters"
        product_desc = product_description.strip() if product_description.strip() else "No extra product description."
        return f"""
Generate {panel_count} comic panels in strict JSON:
{{
  "panels": [
    {{
      "index": 1,
      "visual_prompt": "string",
      "dialogue": "string",
      "emotion": "string",
      "product_focus": "string"
    }}
  ]
}}

Language: {language_text}
Product: {product_name}
Product description: {product_desc}
Character setup: {characters}
Style: {style_desc}
Aspect ratio: {ratio_label} ({ratio_size})

Storyboard beats:
{storyboard_json}

Hard constraints:
- Return JSON only.
- No extra keys.
- dialogue must be <= 20 characters.
- dialogue must be natural spoken words, not manual/instruction style.
- Every visual_prompt must include: camera angle, subject action, background anchor, and lighting direction.
- Do not use split-screen, before-after collage, or half-frame lighting split in any panel.
- Panel 4 must be a single coherent shot that continues panel 3 with clear narrative progress.
- If a storyboard beat mentions comparison, express it as a single-scene improvement shot, not a split layout.
""".strip()

    @staticmethod
    async def _post_chat_completion(
        *,
        endpoint: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> Optional[dict]:
        request_json = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(endpoint, headers=headers, json=request_json)
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None

        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _normalize_panel_items(
        data: dict,
        *,
        panel_count: int,
        product_name: str,
    ) -> tuple[list[dict], bool]:
        panels = data.get("panels")
        if not isinstance(panels, list):
            return [], False

        normalized: list[dict] = []
        seen_indexes: set[int] = set()
        all_dialogue_present = True

        for i, raw in enumerate(panels, start=1):
            if not isinstance(raw, dict):
                continue
            index_raw = raw.get("index", i)
            try:
                index = int(index_raw)
            except (TypeError, ValueError):
                index = i

            if index < 1 or index > panel_count or index in seen_indexes:
                continue
            seen_indexes.add(index)

            visual_prompt = ComicPromptService._compact_text(str(raw.get("visual_prompt", "")))
            dialogue = ComicPromptService._normalize_dialogue(
                str(raw.get("dialogue", "")),
                ComicPromptService.MAX_DIALOGUE_CHARS,
            )
            emotion = ComicPromptService._compact_text(str(raw.get("emotion", "")))
            product_focus = ComicPromptService._compact_text(str(raw.get("product_focus", "")))

            if not dialogue:
                all_dialogue_present = False

            if not visual_prompt:
                continue

            normalized.append(
                {
                    "index": index,
                    "visual_prompt": visual_prompt,
                    "dialogue": dialogue,
                    "emotion": emotion or "focused",
                    "product_focus": product_focus or product_name,
                }
            )

        normalized.sort(key=lambda x: x["index"])
        return normalized, all_dialogue_present

    @staticmethod
    async def _polish_dialogue(
        *,
        endpoint: str,
        api_key: str,
        model: str,
        language: str,
        dialogue: str,
        emotion: str,
        product_focus: str,
    ) -> str:
        language_text = ComicPromptService._language_text(language)
        system_prompt = (
            "You are a dialogue polisher for comic ads.\n"
            "Return strict JSON only: {\"dialogue\":\"string\"}\n"
            "Keep meaning unchanged, but make it more spoken and emotional.\n"
            "Must remain <= 20 characters."
        )
        user_prompt = (
            f"Language: {language_text}\n"
            f"Original dialogue: {dialogue}\n"
            f"Emotion: {emotion}\n"
            f"Product focus: {product_focus}\n"
            'Return only {"dialogue":"..."}'
        )
        payload = await ComicPromptService._post_chat_completion(
            endpoint=endpoint,
            api_key=api_key,
            model=model or ComicPromptService.DIALOGUE_POLISH_MODEL,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.4,
        )
        if not payload:
            return dialogue

        content = ComicPromptService._extract_text_content(payload)
        if not content:
            return dialogue

        data = ComicPromptService._load_json_object(content)
        if not data:
            return dialogue

        polished = ComicPromptService._normalize_dialogue(
            str(data.get("dialogue", "")),
            ComicPromptService.MAX_DIALOGUE_CHARS,
        )
        return polished or dialogue

    @staticmethod
    async def _maybe_polish_dialogues(
        *,
        endpoint: str,
        api_key: str,
        model: str,
        language: str,
        text_mode: str,
        panels: list[dict],
    ) -> list[dict]:
        if text_mode != "model_text":
            return panels

        polished: list[dict] = []
        for panel in panels:
            dialogue = panel.get("dialogue", "")
            if not dialogue:
                polished.append(panel)
                continue
            new_dialogue = await ComicPromptService._polish_dialogue(
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                language=language,
                dialogue=dialogue,
                emotion=str(panel.get("emotion", "")),
                product_focus=str(panel.get("product_focus", "")),
            )
            next_panel = dict(panel)
            next_panel["dialogue"] = new_dialogue
            polished.append(next_panel)
        return polished

    @staticmethod
    async def generate_panel_prompts(
        *,
        api_key: str,
        base_url: str,
        model: str,
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
        system_prompt = ComicPromptService._build_system_prompt()
        user_prompt = ComicPromptService._build_user_prompt(
            panel_count=panel_count,
            product_name=product_name,
            product_description=product_description,
            character_hint=character_hint,
            style_desc=style_desc,
            language_text=language_text,
            ratio_label=ratio_label,
            ratio_size=ratio_size,
            storyboard_json=storyboard_json,
        )

        attempts = ComicPromptService.MAX_RETRIES + 1
        for _ in range(attempts):
            payload = await ComicPromptService._post_chat_completion(
                endpoint=endpoint,
                api_key=api_key,
                model=model or ComicPromptService.PROMPT_MODEL,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.6,
            )
            if not payload:
                continue

            content = ComicPromptService._extract_text_content(payload)
            if not content:
                continue

            data = ComicPromptService._load_json_object(content)
            if not data:
                continue

            panels, all_dialogue_present = ComicPromptService._normalize_panel_items(
                data=data,
                panel_count=panel_count,
                product_name=product_name,
            )
            if not panels:
                continue
            if not all_dialogue_present:
                continue

            return await ComicPromptService._maybe_polish_dialogues(
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                language=language,
                text_mode=text_mode,
                panels=panels,
            )

        return []
