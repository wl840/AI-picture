from __future__ import annotations

import base64
import binascii
import logging
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import HTTPException

from ..poster_config import ASPECT_RATIOS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"

logger = logging.getLogger(__name__)


class ImageProviderService:
    @staticmethod
    def _save_base64_image(image_b64: str) -> str:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        file_name = f"generated_{uuid.uuid4().hex}.png"
        target = GENERATED_DIR / file_name
        target.write_bytes(base64.b64decode(image_b64))
        return file_name

    @staticmethod
    def _is_dashscope(model: str, base_url: str) -> bool:
        base = base_url.lower()
        return "dashscope.aliyuncs.com" in base or model.lower().startswith("qwen-image")

    @staticmethod
    def _dashscope_generation_url(base_url: str) -> str:
        lower = base_url.lower().rstrip("/")

        if lower.endswith("/services/aigc/multimodal-generation/generation"):
            return base_url
        if "dashscope.aliyuncs.com" not in lower:
            raise HTTPException(
                status_code=400,
                detail=(
                    "当前模型应走 DashScope 图像接口，但 base_url 不是 dashscope 域名。"
                    "请使用 https://dashscope.aliyuncs.com/compatible-mode/v1 "
                    "或 https://dashscope.aliyuncs.com/api/v1"
                ),
            )
        if "/compatible-mode/" in lower:
            return "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        if lower.endswith("/api/v1"):
            return f"{base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
        if lower.endswith("/api"):
            return f"{base_url.rstrip('/')}/v1/services/aigc/multimodal-generation/generation"
        return "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    @staticmethod
    def _build_dashscope_payload(
        *,
        model: str,
        prompt: str,
        size: str,
        logo_base64_data_url: Optional[str],
    ) -> dict:
        content: list[dict[str, str]] = []
        if logo_base64_data_url:
            content.append({"image": logo_base64_data_url})
        content.append({"text": prompt})

        return {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": {
                "size": size.replace("x", "*"),
                "n": 1,
            },
        }

    @staticmethod
    def _build_openai_payload(
        *,
        model: str,
        prompt: str,
        size: str,
        logo_base64_data_url: Optional[str],
    ) -> tuple[str, dict]:
        if logo_base64_data_url:
            return (
                "/responses",
                {
                    "model": model,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {"type": "input_image", "image_url": logo_base64_data_url},
                            ],
                        }
                    ],
                    "tools": [{"type": "image_generation"}],
                },
            )

        return (
            "/images/generations",
            {
                "model": model,
                "prompt": prompt,
                "size": size,
            },
        )

    @staticmethod
    def _as_saved_base64_result(raw: str) -> Optional[dict]:
        try:
            base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return None

        file_name = ImageProviderService._save_base64_image(raw)
        return {
            "image_base64": raw,
            "saved_path": f"/static/generated/{file_name}",
        }

    @staticmethod
    def _extract_image_result(payload: dict) -> Optional[dict]:
        data = payload.get("data")
        if isinstance(data, list) and data:
            item = data[0]
            if isinstance(item, dict):
                if isinstance(item.get("url"), str):
                    return {"image_url": item["url"]}
                if isinstance(item.get("b64_json"), str):
                    b64 = item["b64_json"]
                    file_name = ImageProviderService._save_base64_image(b64)
                    return {
                        "image_base64": b64,
                        "saved_path": f"/static/generated/{file_name}",
                    }

        output = payload.get("output")
        if isinstance(output, list):
            for out in output:
                if not isinstance(out, dict):
                    continue
                content = out.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if isinstance(c.get("image_base64"), str):
                        b64 = c["image_base64"]
                        file_name = ImageProviderService._save_base64_image(b64)
                        return {
                            "image_base64": b64,
                            "saved_path": f"/static/generated/{file_name}",
                        }
                    if isinstance(c.get("result"), str):
                        maybe = ImageProviderService._as_saved_base64_result(c["result"])
                        if maybe:
                            return maybe

        output_obj = payload.get("output")
        if isinstance(output_obj, dict):
            choices = output_obj.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0] if isinstance(choices[0], dict) else None
                if first:
                    message = first.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, list):
                            for item in content:
                                if not isinstance(item, dict):
                                    continue
                                for key in ("image", "url", "image_url"):
                                    val = item.get(key)
                                    if isinstance(val, str):
                                        if val.startswith("http://") or val.startswith("https://") or val.startswith("data:image"):
                                            return {"image_url": val}
                                        maybe = ImageProviderService._as_saved_base64_result(val)
                                        if maybe:
                                            return maybe

        return None

    @staticmethod
    def _build_upstream_error_detail(
        *, provider: str, endpoint: str, response: httpx.Response
    ) -> str:
        request_id = (
            response.headers.get("x-request-id")
            or response.headers.get("x-dashscope-request-id")
            or response.headers.get("request-id")
            or "unknown"
        )
        body = (response.text or "").strip()
        if len(body) > 2000:
            body = f"{body[:2000]}...(truncated)"
        if not body:
            body = "<empty>"

        return (
            f"[{provider}] 上游图片生成失败 | status={response.status_code} "
            f"| request_id={request_id} | endpoint={endpoint} | body={body}"
        )

    @staticmethod
    async def generate_image(
        *,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str,
        ratio_key: str,
        logo_base64_data_url: Optional[str] = None,
    ) -> dict:
        size = ASPECT_RATIOS.get(ratio_key, ASPECT_RATIOS["square"])["size"]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        is_dashscope = ImageProviderService._is_dashscope(model=model, base_url=base_url)

        if is_dashscope:
            provider = "dashscope"
            endpoint = ImageProviderService._dashscope_generation_url(base_url)
            request_json = ImageProviderService._build_dashscope_payload(
                model=model,
                prompt=prompt,
                size=size,
                logo_base64_data_url=logo_base64_data_url,
            )
        else:
            provider = "openai-compatible"
            path, request_json = ImageProviderService._build_openai_payload(
                model=model,
                prompt=prompt,
                size=size,
                logo_base64_data_url=logo_base64_data_url,
            )
            endpoint = f"{base_url.rstrip('/')}{path}"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(endpoint, headers=headers, json=request_json)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"[{provider}] 调用上游失败 | endpoint={endpoint} | "
                    f"error={exc.__class__.__name__}: {exc}"
                ),
            ) from exc

        if response.status_code >= 400:
            detail = ImageProviderService._build_upstream_error_detail(
                provider=provider,
                endpoint=endpoint,
                response=response,
            )
            logger.error("%s", detail)
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            payload = response.json()
        except ValueError as exc:
            body = (response.text or "").strip()
            if len(body) > 1000:
                body = f"{body[:1000]}...(truncated)"
            raise HTTPException(
                status_code=502,
                detail=(
                    f"[{provider}] 上游返回非 JSON | endpoint={endpoint} "
                    f"| status={response.status_code} | body={body or '<empty>'}"
                ),
            ) from exc

        parsed = ImageProviderService._extract_image_result(payload)
        if parsed:
            return parsed

        preview = str(payload)
        if len(preview) > 1500:
            preview = f"{preview[:1500]}...(truncated)"
        raise HTTPException(
            status_code=502,
            detail=f"[{provider}] 无法解析图片结果 | endpoint={endpoint} | payload={preview}",
        )
