"""Smart router — picks model(s)/expert(s) from architecture registry."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from neuralrouter.config import MAX_COLLABORATIVE_EXPERTS, REGISTRY_DIR


@dataclass
class ExpertMatch:
    model_id: str
    expert_id: str
    expert_name: str
    matched_keywords: list[str] = field(default_factory=list)
    score: int = 0


def load_registry() -> dict:
    registry: dict = {}
    if not REGISTRY_DIR.exists():
        raise RuntimeError(f"Registry directory not found: {REGISTRY_DIR}")

    for file in sorted(REGISTRY_DIR.glob("*.json")):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            registry[data["model_id"]] = data

    if not registry:
        raise RuntimeError(f"No model registry files in {REGISTRY_DIR}")
    return registry


REGISTRY = load_registry()


def activate_experts(query: str) -> list[ExpertMatch]:
    q = query.lower()
    matches: list[ExpertMatch] = []

    for model_id, model_data in REGISTRY.items():
        best_for_model: ExpertMatch | None = None
        for expert in model_data.get("sub_experts", []):
            matched = [kw for kw in expert.get("keywords", []) if kw.lower() in q]
            if matched:
                candidate = ExpertMatch(
                    model_id=model_id,
                    expert_id=expert["id"],
                    expert_name=expert["name"],
                    matched_keywords=matched,
                    score=len(matched),
                )
                if best_for_model is None or candidate.score > best_for_model.score:
                    best_for_model = candidate
        if best_for_model:
            matches.append(best_for_model)

    if not matches:
        return [
            ExpertMatch(
                model_id="qwen",
                expert_id="general-expert",
                expert_name="General response",
                matched_keywords=[],
                score=0,
            )
        ]

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:MAX_COLLABORATIVE_EXPERTS]


def confidence_for(match: ExpertMatch) -> float:
    return min(0.55 + match.score * 0.12, 0.97)


def manual_expert(model_id: str) -> ExpertMatch:
    if model_id not in REGISTRY:
        raise ValueError(f"unknown model '{model_id}'")
    return ExpertMatch(
        model_id=model_id,
        expert_id="manual-override",
        expert_name="Manual override",
        matched_keywords=[],
        score=5,
    )
