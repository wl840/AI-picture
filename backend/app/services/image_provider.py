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

        if lower.endswith("dashscope.aliyuncs.com"):
            return "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

        if "/api/v1/" in lower:
            return f"{base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"

        return "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    @staticmethod
    def _build_dashscope_payload(
        *,
        model: str,
        prompt: str,
        size: str,
        image_inputs: Optional[list[str]] = None,
    ) -> dict:
        content: list[dict[str, str]] = []
        for img in image_inputs or []:
            content.append({"image": img})
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
                                {
                                    "type": "input_image",
                                    "image_url": logo_base64_data_url,
                                },
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
                                    if isinstance(val, dict):
                                        nested_url = val.get("url") or val.get("image_url")
                                        if isinstance(nested_url, str):
                                            return {"image_url": nested_url}

            results = output_obj.get("results")
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict):
                    url = first.get("url") or first.get("image_url")
                    if isinstance(url, str):
                        return {"image_url": url}
                    b64 = first.get("b64_json")
                    if isinstance(b64, str):
                        file_name = ImageProviderService._save_base64_image(b64)
                        return {
                            "image_base64": b64,
                            "saved_path": f"/static/generated/{file_name}",
                        }

        return None

    @staticmethod
    def _build_upstream_error_detail(
        *, provider: str, endpoint: str, response: httpx.Response, stage: str
    ) -> str:
        request_id = (
            response.headers.get("x-request-id")
            or response.headers.get("x-dashscope-request-id")
            or response.headers.get("request-id")
            or "unknown"
        )

        body = response.text or ""
        body = body.strip()
        if len(body) > 2000:
            body = f"{body[:2000]}...(truncated)"
        if not body:
            body = "<empty>"

        return (
            f"[{provider}] 上游图片生成失败 | stage={stage} | status={response.status_code} "
            f"| request_id={request_id} | endpoint={endpoint} | body={body}"
        )

    @staticmethod
    async def _post_or_raise(
        *,
        client: httpx.AsyncClient,
        endpoint: str,
        headers: dict,
        request_json: dict,
        provider: str,
        stage: str,
    ) -> dict:
        try:
            response = await client.post(endpoint, headers=headers, json=request_json)
        except httpx.RequestError as exc:
            logger.exception("Upstream request error provider=%s stage=%s endpoint=%s", provider, stage, endpoint)
            raise HTTPException(
                status_code=502,
                detail=(
                    f"[{provider}] 调用上游失败 | stage={stage} | endpoint={endpoint} | "
                    f"error={exc.__class__.__name__}: {exc}"
                ),
            ) from exc

        if response.status_code >= 400:
            detail = ImageProviderService._build_upstream_error_detail(
                provider=provider,
                endpoint=endpoint,
                response=response,
                stage=stage,
            )
            logger.error("%s", detail)
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            return response.json()
        except ValueError as exc:
            body = (response.text or "").strip()
            if len(body) > 1000:
                body = f"{body[:1000]}...(truncated)"
            raise HTTPException(
                status_code=502,
                detail=(
                    f"[{provider}] 上游返回非 JSON | stage={stage} | endpoint={endpoint} "
                    f"| status={response.status_code} | body={body or '<empty>'}"
                ),
            ) from exc

    @staticmethod
    def _result_to_data_url(result: dict) -> str:
        image_url = result.get("image_url")
        if isinstance(image_url, str) and (image_url.startswith("http://") or image_url.startswith("https://") or image_url.startswith("data:image")):
            return image_url

        b64 = result.get("image_base64")
        if isinstance(b64, str):
            return f"data:image/png;base64,{b64}"

        saved_path = result.get("saved_path")
        if isinstance(saved_path, str) and saved_path.startswith("/static/generated/"):
            filename = saved_path.rsplit("/", 1)[-1]
            file_path = GENERATED_DIR / filename
            if file_path.exists():
                encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
                return f"data:image/png;base64,{encoded}"

        raise HTTPException(status_code=502, detail="无法将基础海报转换为二次编辑输入")

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
        if model.lower().startswith("qwen-image") and "dashscope.aliyuncs.com" not in base_url.lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    "qwen-image 模型请使用 DashScope 域名。"
                    "建议 base_url=https://dashscope.aliyuncs.com/compatible-mode/v1"
                ),
            )

        if is_dashscope:
            provider = "dashscope"
            endpoint = ImageProviderService._dashscope_generation_url(base_url)
            async with httpx.AsyncClient(timeout=120) as client:
                if logo_base64_data_url:
                    base_payload = ImageProviderService._build_dashscope_payload(
                        model=model,
                        prompt=prompt,
                        size=size,
                        image_inputs=None,
                    )
                    base_json = await ImageProviderService._post_or_raise(
                        client=client,
                        endpoint=endpoint,
                        headers=headers,
                        request_json=base_payload,
                        provider=provider,
                        stage="logo_base_generate",
                    )
                    base_result = ImageProviderService._extract_image_result(base_json)
                    if not base_result:
                        preview = str(base_json)
                        if len(preview) > 1000:
                            preview = f"{preview[:1000]}...(truncated)"
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                "[dashscope] 基础海报生成成功但无法解析图片 | "
                                f"stage=logo_base_generate | payload={preview}"
                            ),
                        )

                    base_image_ref = ImageProviderService._result_to_data_url(base_result)
                    edit_prompt = (
                        "在不改变海报主体构图、文案内容与风格的前提下，"
                        "把第二张图作为品牌 Logo 角标放在右下角或右上角，"
                        "Logo 宽度约为画面宽度 5%-8%，不得居中、不得放大为主体、不得遮挡主标题。"
                    )
                    edit_payload = ImageProviderService._build_dashscope_payload(
                        model="qwen-image-edit",
                        prompt=edit_prompt,
                        size=size,
                        image_inputs=[base_image_ref, logo_base64_data_url],
                    )
                    edit_json = await ImageProviderService._post_or_raise(
                        client=client,
                        endpoint=endpoint,
                        headers=headers,
                        request_json=edit_payload,
                        provider=provider,
                        stage="logo_edit_merge",
                    )
                    parsed = ImageProviderService._extract_image_result(edit_json)
                    if parsed:
                        return parsed

                    preview = str(edit_json)
                    if len(preview) > 1500:
                        preview = f"{preview[:1500]}...(truncated)"
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "[dashscope] Logo 融合阶段无法解析图片结果 | "
                            f"stage=logo_edit_merge | payload={preview}"
                        ),
                    )

                request_json = ImageProviderService._build_dashscope_payload(
                    model=model,
                    prompt=prompt,
                    size=size,
                    image_inputs=None,
                )
                payload = await ImageProviderService._post_or_raise(
                    client=client,
                    endpoint=endpoint,
                    headers=headers,
                    request_json=request_json,
                    provider=provider,
                    stage="text2image",
                )
                parsed = ImageProviderService._extract_image_result(payload)
                if parsed:
                    return parsed

                payload_preview = str(payload)
                if len(payload_preview) > 1500:
                    payload_preview = f"{payload_preview[:1500]}...(truncated)"
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "[dashscope] 无法解析图片结果 | stage=text2image | "
                        f"payload={payload_preview}"
                    ),
                )

        provider = "openai-compatible"
        path, request_json = ImageProviderService._build_openai_payload(
            model=model,
            prompt=prompt,
            size=size,
            logo_base64_data_url=logo_base64_data_url,
        )
        endpoint = f"{base_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=120) as client:
            payload = await ImageProviderService._post_or_raise(
                client=client,
                endpoint=endpoint,
                headers=headers,
                request_json=request_json,
                provider=provider,
                stage="single_call",
            )

        parsed = ImageProviderService._extract_image_result(payload)
        if parsed:
            return parsed

        payload_preview = str(payload)
        if len(payload_preview) > 1500:
            payload_preview = f"{payload_preview[:1500]}...(truncated)"
        raise HTTPException(
            status_code=502,
            detail=(
                f"[{provider}] 无法解析图片结果 | endpoint={endpoint} | "
                f"payload={payload_preview}"
            ),
        )
