from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class GeneratePosterRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="DashScope/OpenAI-compatible API key")
    model: str = Field(default="wan2.7-image-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/api/v1")
    template_key: str = Field(default="festival_promo")
    style: str = Field(default="american_impasto")
    ratio_key: str = Field(default="square")
    product_name: str = Field(..., min_length=2, max_length=80)
    highlights: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(default="")
    logo_id: Optional[str] = None
    logo_mode: Literal["fixed", "ai"] = Field(default="fixed")
    logo_position: Optional[Literal["top_left", "top_right", "bottom_left", "bottom_right"]] = Field(
        default="top_right"
    )

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def normalize_logo_settings(self) -> "GeneratePosterRequest":
        if self.logo_mode == "fixed" and not self.logo_position:
            self.logo_position = "top_right"
        if self.logo_mode == "ai":
            self.logo_position = None
        return self


class GeneratePosterResponse(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    saved_path: Optional[str] = None
    prompt: str


class PostprocessImageRequest(BaseModel):
    image_paths: List[str] = Field(..., min_length=1, description="List of /static/generated/... paths")
    process_mode: Literal["local", "ai"] = Field(default="local")

    logo_id: Optional[str] = Field(default=None, min_length=8)
    logo_position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = Field(default="top_right")
    logo_scale: float = Field(default=0.2, ge=0.05, le=0.8)
    logo_opacity: float = Field(default=1.0, ge=0.1, le=1.0)

    watermark_text: str = Field(default="", max_length=120)
    watermark_position: Literal["top_left", "top_right", "bottom_left", "bottom_right", "center"] = Field(
        default="bottom_right"
    )
    watermark_font_scale: float = Field(default=0.035, ge=0.01, le=0.2)
    watermark_opacity: float = Field(default=0.38, ge=0.05, le=1.0)
    watermark_color: str = Field(default="#FFFFFF", min_length=4, max_length=9)

    text_content: str = Field(default="", max_length=180)
    text_position: Literal["top_left", "top_right", "bottom_left", "bottom_right", "center"] = Field(
        default="top_left"
    )
    text_font_scale: float = Field(default=0.045, ge=0.01, le=0.2)
    text_opacity: float = Field(default=0.95, ge=0.05, le=1.0)
    text_color: str = Field(default="#FFFFFF", min_length=4, max_length=9)

    api_key: Optional[str] = Field(default=None, min_length=10, description="Required when process_mode=ai")
    model: str = Field(default="wan2.7-image-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/api/v1")
    ai_prompt: str = Field(
        default="在保持原图主体构图与风格的前提下，融合参考logo到画面中，保证清晰、自然、不遮挡主体，不要水印和乱码。",
        max_length=6000,
    )
    ai_ratio_key: Literal["square", "mobile", "landscape"] = Field(default="square")

    @field_validator("image_paths")
    @classmethod
    def normalize_image_paths(cls, value: List[str]) -> List[str]:
        normalized = []
        for item in value:
            path = item.strip()
            if path and path not in normalized:
                normalized.append(path)
        if not normalized:
            raise ValueError("image_paths cannot be empty")
        return normalized

    @field_validator("watermark_text", "text_content")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("model")
    @classmethod
    def normalize_model_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.lower() == "qwen-image-edit-max":
            return "qwen-image-edit-max"
        return normalized

    @model_validator(mode="after")
    def require_any_overlay(self) -> "PostprocessImageRequest":
        if self.process_mode == "ai":
            if not self.api_key:
                raise ValueError("api_key is required when process_mode=ai")
            return self

        if self.logo_id:
            return self
        if self.watermark_text:
            return self
        if self.text_content:
            return self
        raise ValueError("At least one overlay is required: logo_id or watermark_text or text_content")


class PostprocessImageItemResponse(BaseModel):
    source_path: str
    saved_path: Optional[str] = None
    error: Optional[str] = None


class PostprocessImageResponse(BaseModel):
    success_count: int
    items: List[PostprocessImageItemResponse]


class GeneratedImageItemResponse(BaseModel):
    record_id: Optional[str] = None
    path: str
    filename: str
    modified_at: float
    size_bytes: int
    source_type: Optional[str] = None
    source_batch_id: Optional[str] = None
    source_slot: Optional[str] = None


class DeleteGeneratedImageRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Generated image path, e.g. /static/generated/xxx.png")


class DeleteGeneratedImageResponse(BaseModel):
    ok: bool
    record_id: Optional[str] = None
    path: str
    deleted_at: str


class ImageRecordItemResponse(BaseModel):
    record_id: str
    path: str
    filename: str
    source_type: str
    source_batch_id: Optional[str] = None
    source_slot: Optional[str] = None
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None
    modified_at: float
    size_bytes: int


class DeleteImageRecordRequest(BaseModel):
    record_id: str = Field(..., min_length=1)


class DeleteImageRecordResponse(BaseModel):
    ok: bool
    record_id: str
    path: str
    deleted_at: str


class UploadLogoResponse(BaseModel):
    logo_id: str
    filename: str
    url: str

class UploadProductImageResponse(BaseModel):
    product_image_id: str
    filename: str
    url: str


class GenerateProductSetRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="DashScope/OpenAI-compatible API key")
    model: str = Field(default="wan2.7-image-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/api/v1")
    product_image_id: str = Field(..., min_length=8)
    product_name: str = Field(..., min_length=2, max_length=80)
    style: str = Field(default="american_impasto")
    ratio_key: str = Field(default="square")
    highlights: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(default="")
    scene_description: Optional[str] = Field(default="")
    specs: List[str] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

class ProductSetItemResponse(BaseModel):
    key: Literal["main", "detail", "selling_point", "scene", "spec"]
    name: str
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    saved_path: Optional[str] = None
    prompt: str
    error: Optional[str] = None


class GenerateProductSetResponse(BaseModel):
    product_image_id: str
    success_count: int
    items: List[ProductSetItemResponse]


class GenerateComicRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="DashScope/OpenAI-compatible API key")
    model: str = Field(default="wan2.7-image-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/api/v1")
    text_api_key: Optional[str] = Field(default=None, min_length=10)
    text_model: str = Field(default="gpt-5.4")
    text_base_url: str = Field(default="https://api.psydo.top/v1")
    product_name: str = Field(..., min_length=2, max_length=80)
    product_image_id: Optional[str] = Field(default=None, min_length=8)
    style: str = Field(default="american_impasto")
    ratio_key: str = Field(default="square")
    composite_ratio_key: Literal["mobile", "landscape"] = Field(default="mobile")
    panel_count: Literal[4, 6] = Field(default=4)
    product_description: str = Field(default="")
    character_description: str = Field(default="")
    language: Literal["zh-CN", "en-US"] = Field(default="zh-CN")
    text_mode: Literal["post_render", "model_text"] = Field(default="model_text")

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("text_base_url")
    @classmethod
    def normalize_text_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def normalize_descriptions(self) -> "GenerateComicRequest":
        # Backward compatibility: old frontend uses character_description.
        if not self.product_description.strip() and self.character_description.strip():
            self.product_description = self.character_description.strip()
        return self


class ComicPanelItem(BaseModel):
    index: int
    scene: str
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    saved_path: Optional[str] = None
    prompt: str
    error: Optional[str] = None


class GenerateComicResponse(BaseModel):
    panel_count: int
    panels: List[ComicPanelItem]
    composite_path: Optional[str] = None


class GenerateComicTaskCreateResponse(BaseModel):
    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    panel_count: int


class ComicTaskPanelItem(BaseModel):
    index: int
    status: Literal["pending", "prompt_ready", "done", "failed"] = "pending"
    scene: str = ""
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    saved_path: Optional[str] = None
    prompt: str = ""
    error: Optional[str] = None


class GenerateComicTaskStatusResponse(BaseModel):
    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    panel_count: int
    completed_count: int
    panels: List[ComicTaskPanelItem]
    composite_path: Optional[str] = None
    error: Optional[str] = None
