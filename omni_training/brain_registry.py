"""
Omni brain version registry — active / candidate / archived.

Training pipeline registers new versions as `candidate`.
When you approve metrics, `promote()` swaps active brain (hot replace).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

REGISTRY_PATH = Path(__file__).parent / "brain_registry.json"

BrainStatus = Literal["active", "candidate", "training", "archived"]
BrainType = Literal["rules", "lora_hf", "lora_local", "inference_url"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Brain registry missing: {REGISTRY_PATH}")
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_registry(data: dict) -> None:
    data["updated_at"] = _now()
    REGISTRY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_active_brain() -> dict:
    reg = load_registry()
    active_id = reg.get("active_version_id")
    versions = reg.get("versions", {})
    if active_id not in versions:
        raise RuntimeError(f"Active brain '{active_id}' not in registry")
    brain = dict(versions[active_id])
    brain["is_active"] = True
    return brain


def list_versions(status: BrainStatus | None = None) -> list[dict]:
    reg = load_registry()
    active_id = reg.get("active_version_id")
    out = []
    for vid, v in reg.get("versions", {}).items():
        if status and v.get("status") != status:
            continue
        row = dict(v)
        row["is_active"] = vid == active_id
        out.append(row)
    return sorted(out, key=lambda x: x.get("created_at", ""), reverse=True)


def register_version(
    version_id: str,
    *,
    label: str,
    brain_type: BrainType,
    artifact: dict | None = None,
    metrics: dict | None = None,
    status: BrainStatus = "candidate",
    description: str = "",
) -> dict:
    reg = load_registry()
    versions = reg.setdefault("versions", {})
    if version_id in versions:
        raise ValueError(f"Version already exists: {version_id}")

    versions[version_id] = {
        "id": version_id,
        "label": label,
        "type": brain_type,
        "status": status,
        "description": description,
        "artifact": artifact or {},
        "metrics": metrics or {},
        "trained_at": _now() if brain_type.startswith("lora") else None,
        "created_at": _now(),
    }
    save_registry(reg)
    return versions[version_id]


def update_metrics(version_id: str, metrics: dict) -> dict:
    reg = load_registry()
    versions = reg.get("versions", {})
    if version_id not in versions:
        raise KeyError(version_id)
    versions[version_id]["metrics"] = {**versions[version_id].get("metrics", {}), **metrics}
    save_registry(reg)
    return versions[version_id]


def mark_training(version_id: str) -> dict:
    reg = load_registry()
    v = reg["versions"][version_id]
    v["status"] = "training"
    save_registry(reg)
    return v


def promote(version_id: str, *, force: bool = False) -> dict:
    """
    Replace active brain with trained candidate.
    Requires manual_approved=true OR eval_score >= OMNI_BRAIN_MIN_EVAL_SCORE unless force.
    """
    min_score = float(os.environ.get("OMNI_BRAIN_MIN_EVAL_SCORE", "0.75"))
    reg = load_registry()
    versions = reg.get("versions", {})
    if version_id not in versions:
        raise KeyError(f"Unknown version: {version_id}")

    candidate = versions[version_id]
    if candidate.get("status") not in ("candidate", "archived"):
        raise ValueError(f"Cannot promote status={candidate.get('status')}")

    metrics = candidate.get("metrics") or {}
    approved = metrics.get("manual_approved") is True
    score = metrics.get("eval_score")
    if not force and not approved:
        if score is None or float(score) < min_score:
            raise ValueError(
                f"Promote blocked: eval_score={score} (min {min_score}) "
                "or set manual_approved=true after your review"
            )

    old_active_id = reg.get("active_version_id")
    if old_active_id and old_active_id in versions:
        versions[old_active_id]["status"] = "archived"
        versions[old_active_id]["archived_at"] = _now()

    candidate["status"] = "active"
    candidate["promoted_at"] = _now()
    reg["active_version_id"] = version_id
    save_registry(reg)

    return {
        "promoted": version_id,
        "previous": old_active_id,
        "active_brain": candidate,
    }


def rollback(version_id: str) -> dict:
    """Emergency rollback — promote a previous archived version."""
    return promote(version_id, force=True)
