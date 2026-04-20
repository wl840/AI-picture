from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "app" / "data"
RECORD_FILE = GENERATED_DIR / "image_records.json"
LEGACY_SOFT_DELETE_FILE = GENERATED_DIR / "generated_images_soft_deleted.json"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

ImageSourceType = Literal["poster", "product_set", "postprocess", "comic", "legacy"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ImageRecordService:
    @staticmethod
    def _normalize_generated_static_path(source_path: str) -> str:
        value = source_path.strip()
        if not value.startswith("/static/generated/"):
            raise HTTPException(status_code=400, detail=f"unsupported generated image path: {value}")

        filename = value.rsplit("/", 1)[-1]
        if not filename:
            raise HTTPException(status_code=400, detail=f"invalid generated image path: {value}")
        return f"/static/generated/{filename}"

    @staticmethod
    def _resolve_generated_local_path(source_path: str) -> Path:
        normalized = ImageRecordService._normalize_generated_static_path(source_path)
        return GENERATED_DIR / normalized.rsplit("/", 1)[-1]

    @staticmethod
    def _infer_source_type_by_filename(filename: str) -> ImageSourceType:
        name = filename.lower()
        if name.startswith("comic_"):
            return "comic"
        if name.startswith("postprocessed_") or name.startswith("postprocess_"):
            return "postprocess"
        return "legacy"

    @staticmethod
    def _load_records_raw() -> list[dict[str, Any]]:
        if not RECORD_FILE.exists():
            return []
        try:
            loaded = json.loads(RECORD_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(loaded, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in loaded:
            if isinstance(item, dict):
                rows.append(item)
        return rows

    @staticmethod
    def _save_records_raw(records: list[dict[str, Any]]) -> None:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        RECORD_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _ensure_seed_records() -> list[dict[str, Any]]:
        records = ImageRecordService._load_records_raw()
        path_to_latest_idx: dict[str, int] = {}
        for idx, row in enumerate(records):
            path = str(row.get("path") or "").strip()
            if path:
                path_to_latest_idx[path] = idx

        changed = False

        # Backfill existing generated files so old history remains visible.
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        for file in GENERATED_DIR.iterdir():
            if not file.is_file() or file.suffix.lower() not in SUPPORTED_EXTS:
                continue
            path = f"/static/generated/{file.name}"
            if path in path_to_latest_idx:
                continue
            ts = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc).isoformat()
            records.append(
                {
                    "id": uuid.uuid4().hex,
                    "path": path,
                    "filename": file.name,
                    "source_type": ImageRecordService._infer_source_type_by_filename(file.name),
                    "source_batch_id": None,
                    "source_slot": None,
                    "created_at": ts,
                    "updated_at": ts,
                    "deleted_at": None,
                    "meta": {},
                }
            )
            path_to_latest_idx[path] = len(records) - 1
            changed = True

        # Migrate legacy path-based soft-delete flags into record-level soft delete.
        if LEGACY_SOFT_DELETE_FILE.exists():
            try:
                legacy = json.loads(LEGACY_SOFT_DELETE_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                legacy = {}
            if isinstance(legacy, dict):
                for raw_path, deleted_at in legacy.items():
                    path = str(raw_path).strip()
                    if not path.startswith("/static/generated/"):
                        continue
                    idx = path_to_latest_idx.get(path)
                    if idx is None:
                        file_name = path.rsplit("/", 1)[-1]
                        ts = str(deleted_at or _utc_now_iso())
                        records.append(
                            {
                                "id": uuid.uuid4().hex,
                                "path": path,
                                "filename": file_name,
                                "source_type": ImageRecordService._infer_source_type_by_filename(file_name),
                                "source_batch_id": None,
                                "source_slot": None,
                                "created_at": ts,
                                "updated_at": ts,
                                "deleted_at": ts,
                                "meta": {"migrated_from_legacy_soft_delete": True},
                            }
                        )
                        path_to_latest_idx[path] = len(records) - 1
                        changed = True
                    else:
                        current = records[idx]
                        if not current.get("deleted_at"):
                            ts = str(deleted_at or _utc_now_iso())
                            current["deleted_at"] = ts
                            current["updated_at"] = ts
                            changed = True

        if changed:
            ImageRecordService._save_records_raw(records)
        return records

    @staticmethod
    def register_saved_image(
        *,
        saved_path: str,
        source_type: ImageSourceType,
        source_batch_id: Optional[str] = None,
        source_slot: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        normalized_path = ImageRecordService._normalize_generated_static_path(saved_path)
        local_path = ImageRecordService._resolve_generated_local_path(normalized_path)
        if not local_path.exists():
            raise HTTPException(status_code=404, detail=f"image not found: {normalized_path}")

        records = ImageRecordService._ensure_seed_records()
        now = _utc_now_iso()
        filename = local_path.name
        meta = meta or {}

        for row in reversed(records):
            if str(row.get("path")) != normalized_path:
                continue
            row["filename"] = filename
            row["source_type"] = source_type
            row["source_batch_id"] = source_batch_id
            row["source_slot"] = source_slot
            row["updated_at"] = now
            row["deleted_at"] = None
            row["meta"] = meta
            ImageRecordService._save_records_raw(records)
            return row

        created = {
            "id": uuid.uuid4().hex,
            "path": normalized_path,
            "filename": filename,
            "source_type": source_type,
            "source_batch_id": source_batch_id,
            "source_slot": source_slot,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "meta": meta,
        }
        records.append(created)
        ImageRecordService._save_records_raw(records)
        return created

    @staticmethod
    def list_image_records(limit: int = 200, include_deleted: bool = False) -> list[dict[str, Any]]:
        records = ImageRecordService._ensure_seed_records()
        items: list[dict[str, Any]] = []
        for row in records:
            path = str(row.get("path") or "").strip()
            if not path:
                continue
            if not include_deleted and row.get("deleted_at"):
                continue
            local_path = GENERATED_DIR / path.rsplit("/", 1)[-1]
            if not local_path.exists() or local_path.suffix.lower() not in SUPPORTED_EXTS:
                continue
            stat = local_path.stat()
            items.append(
                {
                    "record_id": str(row.get("id") or ""),
                    "path": path,
                    "filename": local_path.name,
                    "source_type": str(row.get("source_type") or "legacy"),
                    "source_batch_id": row.get("source_batch_id"),
                    "source_slot": row.get("source_slot"),
                    "created_at": str(row.get("created_at") or ""),
                    "updated_at": str(row.get("updated_at") or ""),
                    "deleted_at": row.get("deleted_at"),
                    "modified_at": stat.st_mtime,
                    "size_bytes": stat.st_size,
                }
            )
        items.sort(key=lambda item: item["modified_at"], reverse=True)
        return items[:limit]

    @staticmethod
    def list_generated_images(limit: int = 200) -> list[dict[str, Any]]:
        # Backward-compatible projection for old frontend shape.
        records = ImageRecordService.list_image_records(limit=limit, include_deleted=False)
        return [
            {
                "record_id": item["record_id"],
                "path": item["path"],
                "filename": item["filename"],
                "modified_at": item["modified_at"],
                "size_bytes": item["size_bytes"],
                "source_type": item["source_type"],
                "source_batch_id": item["source_batch_id"],
                "source_slot": item["source_slot"],
            }
            for item in records
        ]

    @staticmethod
    def soft_delete_record(record_id: str) -> dict[str, Any]:
        value = str(record_id or "").strip()
        if not value:
            raise HTTPException(status_code=400, detail="record_id is required")

        records = ImageRecordService._ensure_seed_records()
        now = _utc_now_iso()
        for row in records:
            if str(row.get("id")) != value:
                continue
            row["deleted_at"] = row.get("deleted_at") or now
            row["updated_at"] = now
            ImageRecordService._save_records_raw(records)
            return {
                "ok": True,
                "record_id": value,
                "path": str(row.get("path") or ""),
                "deleted_at": str(row.get("deleted_at")),
            }

        raise HTTPException(status_code=404, detail="record not found")

    @staticmethod
    def soft_delete_by_path(source_path: str) -> dict[str, Any]:
        normalized_path = ImageRecordService._normalize_generated_static_path(source_path)
        local_path = GENERATED_DIR / normalized_path.rsplit("/", 1)[-1]
        if not local_path.exists():
            raise HTTPException(status_code=404, detail=f"image not found: {normalized_path}")

        records = ImageRecordService._ensure_seed_records()
        now = _utc_now_iso()
        for row in reversed(records):
            if str(row.get("path")) != normalized_path:
                continue
            row["deleted_at"] = row.get("deleted_at") or now
            row["updated_at"] = now
            ImageRecordService._save_records_raw(records)
            return {
                "ok": True,
                "record_id": str(row.get("id") or ""),
                "path": normalized_path,
                "deleted_at": str(row.get("deleted_at")),
            }

        created = ImageRecordService.register_saved_image(
            saved_path=normalized_path,
            source_type=ImageRecordService._infer_source_type_by_filename(local_path.name),
        )
        return ImageRecordService.soft_delete_record(str(created.get("id") or ""))
