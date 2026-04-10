from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .poster_config import ASPECT_RATIOS, STYLES, TEMPLATES
from .prompt_engineering import build_poster_prompt
from .schemas import GeneratePosterRequest, GeneratePosterResponse, UploadLogoResponse
from .services.image_provider import ImageProviderService
from .services.storage import StorageService

app = FastAPI(title="AI Poster Module API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"
UPLOAD_DIR = PROJECT_ROOT / "app" / "uploads"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")
app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/poster/options")
async def poster_options() -> dict:
    return {
        "templates": TEMPLATES,
        "styles": STYLES,
        "aspect_ratios": ASPECT_RATIOS,
    }


@app.post("/api/poster/upload-logo", response_model=UploadLogoResponse)
async def upload_logo(file: UploadFile = File(...)) -> UploadLogoResponse:
    logo_id, filename = await StorageService.save_logo(file)
    return UploadLogoResponse(
        logo_id=logo_id,
        filename=filename,
        url=f"/static/uploads/{filename}",
    )


@app.post("/api/poster/generate", response_model=GeneratePosterResponse)
async def generate_poster(req: GeneratePosterRequest) -> GeneratePosterResponse:
    logo_filename = None
    logo_data_url = None

    if req.logo_id:
        matches = list(UPLOAD_DIR.glob(f"{req.logo_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="logo_id 无效或文件不存在")
        logo_filename = matches[0].name
        logo_data_url = StorageService.logo_to_data_url(logo_filename)

    prompt = build_poster_prompt(
        template_key=req.template_key,
        product_name=req.product_name,
        highlights=req.highlights,
        style=req.style,
        description=req.description,
        ratio_key=req.ratio_key,
        logo_filename=logo_filename,
    )

    generated = await ImageProviderService.generate_image(
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        prompt=prompt,
        ratio_key=req.ratio_key,
        logo_base64_data_url=logo_data_url,
    )

    return GeneratePosterResponse(prompt=prompt, **generated)
