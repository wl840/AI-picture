from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .poster_config import ASPECT_RATIOS, STYLES, TEMPLATES
from .schemas import (
    ComicPanelItem,
    DeleteImageRecordRequest,
    DeleteImageRecordResponse,
    DeleteGeneratedImageRequest,
    DeleteGeneratedImageResponse,
    GeneratedImageItemResponse,
    GenerateComicRequest,
    GenerateComicResponse,
    GenerateComicTaskCreateResponse,
    GenerateComicTaskStatusResponse,
    GeneratePosterRequest,
    GeneratePosterResponse,
    GenerateProductSetRequest,
    GenerateProductSetResponse,
    ImageRecordItemResponse,
    PostprocessImageRequest,
    PostprocessImageResponse,
    UploadLogoResponse,
    UploadProductImageResponse,
)
from .services.comic_service import ComicService
from .services.comic_task_service import ComicTaskService
from .services.image_record_service import ImageRecordService
from .services.postprocess_service import PostprocessService
from .services.poster_service import PosterService
from .services.product_set_service import ProductSetService
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
        "styles": [{"key": s["key"], "name": s["name"]} for s in STYLES],
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
    result = await PosterService.generate_poster(req, UPLOAD_DIR)
    return GeneratePosterResponse(**result)


@app.post("/api/poster/postprocess", response_model=PostprocessImageResponse)
async def postprocess_images(req: PostprocessImageRequest) -> PostprocessImageResponse:
    result = await PostprocessService.postprocess_images(req, UPLOAD_DIR)
    return PostprocessImageResponse(**result)


@app.get("/api/poster/generated-images", response_model=list[GeneratedImageItemResponse])
async def list_generated_images() -> list[GeneratedImageItemResponse]:
    items = PostprocessService.list_generated_images()
    return [GeneratedImageItemResponse(**item) for item in items]


@app.get("/api/poster/image-records", response_model=list[ImageRecordItemResponse])
async def list_image_records() -> list[ImageRecordItemResponse]:
    items = ImageRecordService.list_image_records()
    return [ImageRecordItemResponse(**item) for item in items]


@app.post("/api/poster/image-records/delete", response_model=DeleteImageRecordResponse)
async def delete_image_record(req: DeleteImageRecordRequest) -> DeleteImageRecordResponse:
    result = ImageRecordService.soft_delete_record(req.record_id)
    return DeleteImageRecordResponse(**result)


@app.post("/api/poster/generated-images/delete", response_model=DeleteGeneratedImageResponse)
async def delete_generated_image(req: DeleteGeneratedImageRequest) -> DeleteGeneratedImageResponse:
    result = PostprocessService.mark_generated_image_deleted(req.path)
    return DeleteGeneratedImageResponse(**result)


@app.post("/api/product/upload-image", response_model=UploadProductImageResponse)
async def upload_product_image(file: UploadFile = File(...)) -> UploadProductImageResponse:
    product_image_id, filename = await StorageService.save_product_image(file)
    return UploadProductImageResponse(
        product_image_id=product_image_id,
        filename=filename,
        url=f"/static/uploads/{filename}",
    )


@app.post("/api/product/generate-set", response_model=GenerateProductSetResponse)
async def generate_product_set(req: GenerateProductSetRequest) -> GenerateProductSetResponse:
    result = await ProductSetService.generate_product_set(req, UPLOAD_DIR)
    return GenerateProductSetResponse(**result)


@app.post("/api/poster/generate-comic", response_model=GenerateComicResponse)
async def generate_comic(req: GenerateComicRequest) -> GenerateComicResponse:
    result = await ComicService.generate_comic(req, UPLOAD_DIR)
    return GenerateComicResponse(
        panel_count=result["panel_count"],
        panels=[ComicPanelItem(**p) for p in result["panels"]],
        composite_path=result.get("composite_path"),
    )


@app.post("/api/poster/generate-comic/task", response_model=GenerateComicTaskCreateResponse)
async def create_comic_task(req: GenerateComicRequest) -> GenerateComicTaskCreateResponse:
    task = await ComicTaskService.create_task(panel_count=req.panel_count)
    asyncio.create_task(ComicTaskService.run_task(task["task_id"], req, UPLOAD_DIR))
    return GenerateComicTaskCreateResponse(
        task_id=task["task_id"],
        status=task["status"],
        panel_count=task["panel_count"],
    )


@app.get("/api/poster/generate-comic/task/{task_id}", response_model=GenerateComicTaskStatusResponse)
async def get_comic_task(task_id: str) -> GenerateComicTaskStatusResponse:
    task = await ComicTaskService.get_task(task_id)
    return GenerateComicTaskStatusResponse(**task)
