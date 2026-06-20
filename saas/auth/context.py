"""Authenticated request context for multi-tenant SaaS."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    """Resolved after API key verification."""

    user_id: str | None  # None for legacy env keys
    api_key_id: str | None
    plan_id: str
    client_label: str  # key prefix for logs / rate limit
    email: str | None = None
    rate_limit_per_minute: int = 60
    max_concurrent: int = 5
    training_opt_in: bool = False
