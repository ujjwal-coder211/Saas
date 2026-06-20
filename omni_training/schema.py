"""
Extended schema — user behavior + model behavior + satisfaction signals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


@dataclass
class ResponsePattern:
    is_chain_of_thought: bool
    language: str
    length_chars: int
    structure: str


@dataclass
class ModelBehaviorProfile:
    """
    How the answering model behaved — NOT just what the user asked.
    Used to teach Omni v2+ each brain's capability and answer style.
    """

    capability_tags: list[str] = field(default_factory=list)
    answer_style: str = "unknown"
    verbosity: str = "medium"
    uses_examples: bool = False
    uses_markdown_structure: bool = False
    registry_style_alignment: float = 0.0
    expert_domain: str = ""
    collaborative_role: str = "primary"
    tokens_used: int | None = None
    latency_s: float | None = None


@dataclass
class SatisfactionSignals:
    """How much the user liked the experience (explicit + implicit)."""

    thumbs: str | None = None
    retry: bool = False
    time_spent_s: float | None = None
    response_time_s: float | None = None
    implicit_score: float = 0.5
    combined_score: float = 0.5


@dataclass
class TrainingRow:
    row_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    query: str = ""
    model_response: str = ""

    model_used: str = ""
    expert_id: str = ""
    router_confidence: float = 0.0
    collaborative: bool = False
    all_experts_used: list[str] = field(default_factory=list)

    architecture_snapshot: dict = field(default_factory=dict)
    response_pattern: Optional[ResponsePattern] = None
    model_behavior: Optional[ModelBehaviorProfile] = None
    satisfaction: Optional[SatisfactionSignals] = None
    user_behavior: dict = field(default_factory=dict)
    code_ast: Optional[dict] = None

    research_notes: dict = field(default_factory=dict)
    quality_score: float | None = None
    train_eligible: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TrainingRow":
        data = dict(data)
        if rp := data.get("response_pattern"):
            if isinstance(rp, dict):
                data["response_pattern"] = ResponsePattern(**rp)
        if mb := data.get("model_behavior"):
            if isinstance(mb, dict):
                data["model_behavior"] = ModelBehaviorProfile(**mb)
        if sat := data.get("satisfaction"):
            if isinstance(sat, dict):
                data["satisfaction"] = SatisfactionSignals(**sat)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
