"""Background agent jobs — async task queue."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

JobStatus = Literal["queued", "running", "done", "failed"]

_jobs: dict[str, dict[str, Any]] = {}


@dataclass
class JobRecord:
    id: str
    status: JobStatus
    task: str
    created_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


def create_job(task: str, user_id: str | None) -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "task": task[:2000],
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "error": None,
    }
    return job_id


def get_job(job_id: str, user_id: str | None) -> dict[str, Any] | None:
    rec = _jobs.get(job_id)
    if not rec:
        return None
    if user_id and rec.get("user_id") and rec["user_id"] != user_id:
        return None
    return rec


def list_jobs(user_id: str | None, limit: int = 20) -> list[dict[str, Any]]:
    items = [j for j in _jobs.values() if not user_id or j.get("user_id") == user_id]
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items[:limit]


async def run_job_async(job_id: str, coro_factory) -> None:
    rec = _jobs.get(job_id)
    if not rec:
        return
    rec["status"] = "running"
    try:
        result = await coro_factory()
        rec["status"] = "done"
        rec["result"] = result
    except Exception as exc:
        rec["status"] = "failed"
        rec["error"] = str(exc)
