"""
Omni Brain loader — Aksh main brain hot-swap.

Reads brain_registry.json on each plan (lightweight JSON).
Active brain type decides: rules controller vs trained LoRA vs inference URL.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from omni_training.brain_registry import get_active_brain, load_registry

logger = logging.getLogger(__name__)

OMNI_INFERENCE_URL = os.environ.get("OMNI_INFERENCE_URL", "")


def active_brain_summary() -> dict[str, Any]:
    try:
        brain = get_active_brain()
        return {
            "version_id": brain["id"],
            "label": brain.get("label"),
            "type": brain.get("type"),
            "status": brain.get("status"),
            "artifact": brain.get("artifact"),
        }
    except Exception as exc:
        logger.warning("Brain registry read failed: %s", exc)
        return {"version_id": "omni-rules-v0", "type": "rules", "fallback": True}


def brain_directives_for_plan() -> list[str]:
    """Extra system directives from active trained brain metadata."""
    brain = get_active_brain()
    btype = brain.get("type", "rules")
    directives: list[str] = []

    if btype == "rules":
        directives.append("Omni controller: rules-based routing (pre-train or fallback).")
    elif btype in ("lora_hf", "lora_local"):
        art = brain.get("artifact") or {}
        directives.append(
            f"Omni trained brain active ({brain.get('id')}): "
            f"prefer patterns from adapter {art.get('adapter_repo') or art.get('adapter_path')}."
        )
        directives.append(
            "Route experts when needed; synthesize in Omni style — Hinglish-friendly, precise."
        )
    elif btype == "inference_url":
        directives.append(f"Omni native inference brain: {brain.get('id')}")

    return directives


async def omni_native_plan_hint(query: str) -> str | None:
    """
    Optional: call external Omni inference for controller decisions.
    Returns extra context string or None.
    Set OMNI_INFERENCE_URL to your GPU service (Colab tunnel / vLLM / TGI).
    """
    brain = get_active_brain()
    if brain.get("type") not in ("lora_hf", "lora_local", "inference_url"):
        return None
    if not OMNI_INFERENCE_URL:
        return None

    import httpx

    payload = {
        "query": query,
        "brain_version": brain.get("id"),
        "artifact": brain.get("artifact"),
        "mode": "controller_hint",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{OMNI_INFERENCE_URL.rstrip('/')}/plan", json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("controller_context") or data.get("hint")
    except Exception:
        logger.exception("Omni inference URL failed — using rules fallback")
        return None


def invalidate_cache() -> None:
    """No-op placeholder — registry read is always fresh from disk for hot-swap."""
