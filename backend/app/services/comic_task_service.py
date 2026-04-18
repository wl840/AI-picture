from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from ..schemas import GenerateComicRequest
from .comic_service import ComicService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ComicTaskService:
    _tasks: dict[str, dict] = {}
    _lock = asyncio.Lock()

    @staticmethod
    def _init_panels(panel_count: int) -> list[dict]:
        return [
            {
                "index": i,
                "status": "pending",
                "scene": "",
                "prompt": "",
                "saved_path": None,
                "image_url": None,
                "image_base64": None,
                "error": None,
            }
            for i in range(1, panel_count + 1)
        ]

    @staticmethod
    def _completed_count(task: dict) -> int:
        return sum(1 for panel in task["panels"] if panel.get("status") in {"done", "failed"})

    @staticmethod
    async def create_task(panel_count: int) -> dict:
        task_id = uuid.uuid4().hex
        now = _now_iso()
        task = {
            "task_id": task_id,
            "status": "pending",
            "panel_count": panel_count,
            "completed_count": 0,
            "panels": ComicTaskService._init_panels(panel_count=panel_count),
            "composite_path": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        async with ComicTaskService._lock:
            ComicTaskService._tasks[task_id] = task
            return copy.deepcopy(task)

    @staticmethod
    async def get_task(task_id: str) -> dict:
        async with ComicTaskService._lock:
            task = ComicTaskService._tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="comic task not found")
            return copy.deepcopy(task)

    @staticmethod
    async def _set_task_fields(task_id: str, **fields: object) -> None:
        async with ComicTaskService._lock:
            task = ComicTaskService._tasks.get(task_id)
            if not task:
                return
            for key, value in fields.items():
                task[key] = value
            task["completed_count"] = ComicTaskService._completed_count(task)
            task["updated_at"] = _now_iso()

    @staticmethod
    async def _update_panel(task_id: str, panel: dict, *, status: str | None = None) -> None:
        async with ComicTaskService._lock:
            task = ComicTaskService._tasks.get(task_id)
            if not task:
                return
            index = int(panel.get("index", 0))
            if index < 1 or index > task["panel_count"]:
                return

            slot = task["panels"][index - 1]
            for key in ("scene", "prompt", "saved_path", "image_url", "image_base64", "error"):
                if key in panel:
                    slot[key] = panel.get(key)
            if status:
                slot["status"] = status
            task["completed_count"] = ComicTaskService._completed_count(task)
            task["updated_at"] = _now_iso()

    @staticmethod
    async def run_task(task_id: str, req: GenerateComicRequest, upload_dir: Path) -> None:
        await ComicTaskService._set_task_fields(task_id, status="running", error=None)

        async def on_progress(event: dict) -> None:
            event_type = str(event.get("type", "")).strip()
            panel = event.get("panel") if isinstance(event.get("panel"), dict) else {}
            if event_type == "panel_prompt":
                await ComicTaskService._update_panel(task_id, panel, status="prompt_ready")
                return
            if event_type == "panel_done":
                await ComicTaskService._update_panel(task_id, panel, status="done")
                return
            if event_type == "panel_error":
                await ComicTaskService._update_panel(task_id, panel, status="failed")

        try:
            result = await ComicService.generate_comic(req, upload_dir, progress_hook=on_progress)

            for panel in result.get("panels", []):
                if not isinstance(panel, dict):
                    continue
                panel_status = "failed" if panel.get("error") else "done"
                await ComicTaskService._update_panel(task_id, panel, status=panel_status)

            await ComicTaskService._set_task_fields(
                task_id,
                status="completed",
                composite_path=result.get("composite_path"),
            )
        except Exception as exc:  # noqa: BLE001
            await ComicTaskService._set_task_fields(task_id, status="failed", error=str(exc))
