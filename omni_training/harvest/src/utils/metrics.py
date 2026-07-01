"""
src/utils/metrics.py

Token & cost tracking. Extracts usage data from an API response and persists
it to its own SQLite table so spend can be queried independently of the
harvested content.
"""

import time
from dataclasses import dataclass


@dataclass
class UsageRecord:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    timestamp: float


class MetricsTracker:
    """
    Call `record()` after every successful API response. Pricing is looked up
    from the `pricing` section of settings.yaml (per-1K-token rates), falling
    back to the `default` entry when a model has no specific rate configured.
    """

    def __init__(self, pricing: dict | None = None):
        self.pricing = pricing or {}
        self.default_pricing = self.pricing.get("default", {
            "prompt_per_1k": 0.0, "completion_per_1k": 0.0
        })
        self._totals = {
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
        }

    def _rates_for(self, model: str) -> dict:
        return self.pricing.get(model, self.default_pricing)

    def compute(self, model: str, response_json: dict) -> UsageRecord:
        usage = response_json.get("usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        rates = self._rates_for(model)
        cost = (
            (prompt_tokens / 1000.0) * rates.get("prompt_per_1k", 0.0)
            + (completion_tokens / 1000.0) * rates.get("completion_per_1k", 0.0)
        )

        self._totals["requests"] += 1
        self._totals["prompt_tokens"] += prompt_tokens
        self._totals["completion_tokens"] += completion_tokens
        self._totals["total_tokens"] += total_tokens
        self._totals["estimated_cost_usd"] += cost

        return UsageRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 8),
            timestamp=time.time(),
        )

    def totals(self) -> dict:
        return dict(self._totals)
