"""SaaS dashboard + tenant management API routes."""

from __future__ import annotations

import os
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from neuralrouter.auth import verify_auth
from saas.auth.api_keys import (
    create_api_key,
    create_user_with_key,
    list_user_keys,
    revoke_api_key,
)
from saas.auth.context import AuthContext
from saas.billing.stripe_webhooks import handle_webhook, stripe_enabled
from saas.billing.usage import get_usage_summary
from saas.db.connection import saas_db_enabled
from sqlalchemy import text

from saas.db.connection import db_session

router = APIRouter(prefix="/saas/v1", tags=["saas"])


class SignupRequest(BaseModel):
    email: EmailStr
    plan_id: Literal["free", "pro", "payg"] = "free"


class CreateKeyRequest(BaseModel):
    name: str = Field(default="default", max_length=64)


class TrainingOptInRequest(BaseModel):
    enabled: bool


@router.get("/health")
async def saas_health():
    return {
        "saas_enabled": saas_db_enabled(),
        "stripe_enabled": stripe_enabled(),
    }


@router.post("/signup")
async def signup(body: SignupRequest):
    """Dev/MVP signup — replace with Clerk webhook in production."""
    if not saas_db_enabled():
        raise HTTPException(503, "DATABASE_URL not configured")
    if os.environ.get("SAAS_ALLOW_PUBLIC_SIGNUP", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(403, "Public signup disabled. Set SAAS_ALLOW_PUBLIC_SIGNUP=true for MVP.")

    try:
        result = create_user_with_key(body.email, body.plan_id)
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(409, "Email already registered") from exc
        raise

    return {
        "user_id": result["user_id"],
        "email": result["email"],
        "plan_id": result["plan_id"],
        "api_key": result["api_key"],
        "message": "Save api_key now — it will not be shown again.",
    }


@router.get("/me")
async def me(auth: Annotated[AuthContext, Depends(verify_auth)]):
    if not auth.user_id:
        return {"mode": "legacy_env_key", "client_label": auth.client_label}
    summary = get_usage_summary(auth.user_id)
    keys = list_user_keys(auth.user_id)
    return {"auth": auth, "usage": summary, "api_keys": keys}


@router.get("/usage")
async def usage(auth: Annotated[AuthContext, Depends(verify_auth)]):
    if not auth.user_id:
        raise HTTPException(400, "Usage tracking requires SaaS API key (DATABASE_URL)")
    return get_usage_summary(auth.user_id)


@router.post("/api-keys")
async def new_api_key(
    body: CreateKeyRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    if not auth.user_id:
        raise HTTPException(400, "Requires SaaS database API key")
    created = create_api_key(auth.user_id, body.name)
    return {
        "api_key": created["api_key"],
        "key_prefix": created["key_prefix"],
        "message": "Save api_key now — shown once only.",
    }


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    if not auth.user_id:
        raise HTTPException(400, "Requires SaaS database API key")
    if not revoke_api_key(auth.user_id, key_id):
        raise HTTPException(404, "Key not found")
    return {"status": "revoked", "key_id": key_id}


@router.patch("/training-opt-in")
async def training_opt_in(
    body: TrainingOptInRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    if not auth.user_id:
        raise HTTPException(400, "Requires SaaS database API key")
    with db_session() as session:
        session.execute(
            text("UPDATE users SET training_opt_in = :v, updated_at = NOW() WHERE id = :uid"),
            {"v": body.enabled, "uid": auth.user_id},
        )
    return {"training_opt_in": body.enabled}


@router.post("/checkout-session")
async def checkout_session(
    auth: Annotated[AuthContext, Depends(verify_auth)],
    plan_id: Literal["pro"] = Query(default="pro"),
):
    """Create Stripe checkout — requires STRIPE_SECRET_KEY + price IDs."""
    import os

    sk = os.environ.get("STRIPE_SECRET_KEY", "")
    price_id = os.environ.get("STRIPE_PRICE_PRO", "")
    if not sk or not price_id or not auth.user_id:
        raise HTTPException(503, "Stripe not configured or legacy key")

    import stripe

    stripe.api_key = sk
    base_url = os.environ.get("SAAS_PUBLIC_URL", "http://localhost:8000")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}/web/dashboard/?success=1",
        cancel_url=f"{base_url}/web/dashboard/?canceled=1",
        customer_email=auth.email,
        metadata={"plan_id": plan_id, "user_id": auth.user_id},
    )
    return {"checkout_url": session.url}
