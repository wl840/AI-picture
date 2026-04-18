from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class GeneratePosterRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="DashScope/OpenAI-compatible API key")
    model: str = Field(default="qwen-image-2.0-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    template_key: str = Field(default="festival_promo")
    style: str = Field(default="american_comic")
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
    model: str = Field(default="qwen-image-2.0-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    product_image_id: str = Field(..., min_length=8)
    product_name: str = Field(..., min_length=2, max_length=80)
    style: str = Field(default="american_comic")
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
    model: str = Field(default="wan2.7-image")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    product_name: str = Field(..., min_length=2, max_length=80)
    product_image_id: Optional[str] = Field(default=None, min_length=8)
    style: str = Field(default="american_comic")
    ratio_key: str = Field(default="square")
    panel_count: int = Field(default=4, ge=4, le=6)
    product_description: str = Field(default="")
    character_description: str = Field(default="")
    language: Literal["zh-CN", "en-US"] = Field(default="zh-CN")
    text_mode: Literal["post_render", "model_text"] = Field(default="post_render")

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
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
