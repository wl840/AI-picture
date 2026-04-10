from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class GeneratePosterRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="DashScope/OpenAI-compatible API key")
    model: str = Field(default="qwen-image-2.0-pro")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    template_key: str = Field(default="festival_promo")
    style: str = Field(default="简约商务")
    ratio_key: str = Field(default="square")
    product_name: str = Field(..., min_length=2, max_length=80)
    highlights: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(default="")
    logo_id: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")


class GeneratePosterResponse(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    saved_path: Optional[str] = None
    prompt: str


class UploadLogoResponse(BaseModel):
    logo_id: str
    filename: str
    url: str
