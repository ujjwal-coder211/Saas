"""Sarva Conductor training schemas — routing, synthesis, production rows.

Paper v6 fields: confidence + self_executable for confidence-gated self-routing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Complexity = Literal["low", "medium", "high"]
WorkerId = Literal["qwen", "deepseek", "glm", "llama", "mistral", "claude", "kimi", "nemotron"]

# Runtime map: training label "nemotron" worker → OpenRouter deepseek slot
WORKER_RUNTIME_MAP: dict[str, str] = {
    "nemotron": "deepseek",
    "kimi": "kimi",
    "mistral": "mistral",
    "glm": "glm",
    "qwen": "qwen",
    "deepseek": "deepseek",
    "llama": "llama",
    "claude": "claude",
}


@dataclass
class RoutingDecision:
    task_type: str = "general"
    complexity: Complexity = "medium"
    primary_model: str = "qwen"
    secondary_models: list[str] = field(default_factory=list)
    parallel: bool = False
    reasoning_mode: bool = False
    use_claude: bool = False
    use_glm: bool = False
    reason: str = ""
    # Paper §4.3 — confidence-gated self-routing
    confidence: float = 0.5
    self_executable: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def runtime_primary(self) -> str:
        return WORKER_RUNTIME_MAP.get(self.primary_model, self.primary_model)

    def runtime_secondaries(self) -> list[str]:
        return [WORKER_RUNTIME_MAP.get(m, m) for m in self.secondary_models]


ROUTING_SYSTEM = (
    "You are Sarva, an intelligent conductor AI. Your job is to analyze any user query "
    "and decide the best routing plan using BOTH rules and reasoning. "
    "Always respond with a valid JSON object only — no explanation, no prose. "
    "JSON fields: primary_model, secondary_models (list), parallel (bool), "
    "complexity (low/medium/high), reasoning_mode (on/off), "
    "confidence (0.0-1.0 — how sure you are you could handle this alone), "
    "self_executable (bool — true ONLY if confidence clears the task bar AND the task "
    "is not high-stakes; never claim you can answer everything), "
    "reason (one line explaining the decision). "
    "If unsure or the task needs fresh facts, set self_executable=false and prefer "
    "delegation or search over guessing."
)

SYNTHESIS_SYSTEM = (
    "You are Sarva, an intelligent conductor AI. Multiple expert AI models have answered a query. "
    "Your job is to synthesize the BEST single answer: combine insights, remove redundancy, "
    "fix errors, and respond clearly. Do not invent facts that no expert stated."
)
