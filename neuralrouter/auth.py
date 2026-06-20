"""API key authentication — env keys (legacy) + PostgreSQL SaaS keys."""

from __future__ import annotations

import hmac
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from neuralrouter.config import ALLOW_UNAUTHENTICATED, NEURALROUTER_API_KEYS
from saas.auth.api_keys import verify_db_api_key
from saas.auth.context import AuthContext
from saas.billing.plans import get_plan
from saas.db.connection import saas_db_enabled


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _env_key_valid(provided: str) -> bool:
    if not NEURALROUTER_API_KEYS:
        return False
    for valid in NEURALROUTER_API_KEYS:
        if hmac.compare_digest(provided, valid):
            return True
    return False


def verify_auth(authorization: Annotated[str | None, Header()] = None) -> AuthContext:
    """
    FastAPI dependency. Returns AuthContext for billing + rate limits.
    Priority: DB key → env key → dev unauth.
    """
    if ALLOW_UNAUTHENTICATED and not NEURALROUTER_API_KEYS and not saas_db_enabled():
        plan = get_plan("free")
        return AuthContext(
            user_id=None,
            api_key_id=None,
            plan_id="free",
            client_label="dev-local",
            rate_limit_per_minute=plan.rate_limit_per_minute,
            max_concurrent=plan.max_concurrent,
        )

    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization: Bearer <api-key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if saas_db_enabled():
        row = verify_db_api_key(token)
        if row:
            return AuthContext(
                user_id=row["user_id"],
                api_key_id=row["api_key_id"],
                plan_id=row["plan_id"],
                client_label=row["key_prefix"],
                email=row["email"],
                rate_limit_per_minute=row["rate_limit_per_minute"],
                max_concurrent=row["max_concurrent"],
                training_opt_in=row["training_opt_in"],
            )

    if _env_key_valid(token):
        plan = get_plan("pro")
        return AuthContext(
            user_id=None,
            api_key_id=None,
            plan_id="pro",
            client_label=token[:8] + "…",
            rate_limit_per_minute=plan.rate_limit_per_minute,
            max_concurrent=plan.max_concurrent,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_api_key(authorization: Annotated[str | None, Header()] = None) -> str:
    """Backward-compatible dependency returning client label string."""
    return verify_auth(authorization).client_label


def generate_api_key() -> str:
    return f"nr_{secrets.token_urlsafe(32)}"
