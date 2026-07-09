"""
Sarva Brain loader — hot-swap + optional trained /plan override.

Reads brain_registry.json on each plan. When SARVA_INFERENCE_URL is set and the
active brain is a trained adapter, calls /plan and returns a structured routing
trace (not just a text hint) so experts are actually overridden.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sarva_training.brain_registry import get_active_brain

from neuralrouter.sarva_brain.routing_policy import (
    RoutingDecisionTrace,
    parse_trained_plan_json,
)

logger = logging.getLogger(__name__)

SARVA_INFERENCE_URL = os.environ.get("SARVA_INFERENCE_URL", "")


def _inference_url(brain: dict | None = None) -> str:
    """Env wins; else artifact.inference_url from registry (set at plug time)."""
    if SARVA_INFERENCE_URL:
        return SARVA_INFERENCE_URL
    try:
        brain = brain or get_active_brain()
        art = brain.get("artifact") or {}
        return str(art.get("inference_url") or "").strip()
    except Exception:
        return ""


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
        return {"version_id": "sarva-rules-v0", "type": "rules", "fallback": True}


def brain_directives_for_plan() -> list[str]:
    """Extra system directives from active trained brain metadata."""
    brain = get_active_brain()
    btype = brain.get("type", "rules")
    directives: list[str] = []

    if btype == "rules":
        directives.append(
            "Sarva controller: hybrid rules + reasoning routing (pre-train or fallback)."
        )
    elif btype in ("lora_hf", "lora_local"):
        art = brain.get("artifact") or {}
        directives.append(
            f"Sarva trained brain active ({brain.get('id')}): "
            f"prefer patterns from adapter {art.get('adapter_repo') or art.get('adapter_path')}."
        )
        directives.append(
            "Route experts when needed; synthesize in Sarva style — Hinglish-friendly, precise."
        )
    elif btype == "inference_url":
        directives.append(f"Sarva native inference brain: {brain.get('id')}")

    return directives


async def sarva_native_plan_hint(query: str) -> str | None:
    """Legacy text hint from /plan — kept for backward compatibility."""
    brain = get_active_brain()
    if brain.get("type") not in ("lora_hf", "lora_local", "inference_url"):
        return None
    if not _inference_url(brain):
        return None
    trace = await sarva_native_plan_trace(query)
    if trace is None:
        return None
    return trace.reasoning_text()


async def sarva_native_plan_trace(query: str) -> RoutingDecisionTrace | None:
    """
    Call external Sarva inference for a structured routing decision.
    Returns RoutingDecisionTrace that overrides activate_experts, or None.
    """
    brain = get_active_brain()
    if brain.get("type") not in ("lora_hf", "lora_local", "inference_url"):
        return None
    url = _inference_url(brain)
    if not url:
        return None

    import httpx

    payload = {
        "query": query,
        "brain_version": brain.get("id"),
        "artifact": brain.get("artifact"),
        "mode": "controller_plan",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{url.rstrip('/')}/plan", json=payload)
            r.raise_for_status()
            data = r.json()
            # Accept either nested plan or flat JSON.
            plan_obj = data.get("plan") if isinstance(data.get("plan"), dict) else data
            trace = parse_trained_plan_json(plan_obj)
            if trace is None:
                hint = data.get("controller_context") or data.get("hint")
                if hint:
                    logger.info("Sarva /plan returned text hint only — no expert override")
                return None
            return trace
    except Exception:
        logger.exception("Sarva inference URL failed — using hybrid rules+reasoning fallback")
        return None


def invalidate_cache() -> None:
    """No-op placeholder — registry read is always fresh from disk for hot-swap."""
