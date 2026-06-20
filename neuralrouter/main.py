"""
NeuralRouter FastAPI — SYSTEM 1 (production SaaS).

Endpoints:
  POST /v1/chat              — simple JSON for web/mobile apps
  POST /v1/chat/completions  — OpenAI-compatible (Cursor, Codex, Continue)
  GET  /v1/models            — OpenAI-compatible model list
  POST /v1/feedback          — user feedback → Omni Training Program
  GET  /health               — health check (no auth)
  /saas/v1/*                 — billing, usage, API keys (see saas/api/routes.py)
"""

from __future__ import annotations

import logging
import sys
import time
import uuid

from neuralrouter.env_loader import load_dotenv  # noqa: F401 — loads .env on import
from typing import Annotated, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from neuralrouter.auth import verify_auth
from saas.auth.context import AuthContext
from neuralrouter.chat_service import run_chat
from neuralrouter.config import (
    APP_NAME,
    APP_VERSION,
    CORS_ORIGINS,
    MAX_MESSAGE_CHARS,
    ROOT_DIR,
)
from saas.rate_limit import rate_limit
from neuralrouter.router import REGISTRY, manual_expert
from neuralrouter.concurrency import ConcurrencyGuard, active_users_summary
from neuralrouter.load_balancer import balancer
from saas.billing.usage import QuotaExceededError, check_quota, record_usage
from saas.billing.stripe_webhooks import handle_webhook
from saas.api.routes import router as saas_router
from saas.api.skills import router as skills_router
from saas.db.connection import saas_db_enabled

sys.path.insert(0, str(ROOT_DIR))
from omni_training.logger import log_interaction, record_feedback  # noqa: E402
from omni_training.vault import verify_admin_key, vault_stats  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("neuralrouter")

app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url="/docs", redoc_url=None)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Omni-Admin-Key", "Stripe-Signature"],
    )

app.include_router(saas_router)
app.include_router(skills_router)

_web_dir = ROOT_DIR / "web"
if _web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(_web_dir), html=True), name="web")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    force_model: Optional[str] = None
    search: Optional[Literal["auto", "on", "off"]] = "auto"

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class ChatResponse(BaseModel):
    row_id: str
    answer: str
    brain_used: str
    all_experts_used: list[str]
    collaborative: bool
    confidence: float
    tokens_used: Optional[int] = None
    web_search_used: bool = False
    omni_controller: Optional[dict] = None


class OpenAIMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., max_length=MAX_MESSAGE_CHARS)


class OpenAIChatRequest(BaseModel):
    model: str = "auto"
    messages: list[OpenAIMessage] = Field(..., min_length=1)
    stream: Optional[bool] = False
    search: Optional[Literal["auto", "on", "off"]] = "auto"


class FeedbackRequest(BaseModel):
    row_id: str
    thumbs: Optional[Literal["up", "down"]] = None
    retry: Optional[bool] = None
    time_spent_s: Optional[float] = Field(None, ge=0, le=86400)


def _messages_to_query(messages: list[OpenAIMessage]) -> str:
    users = [m.content for m in messages if m.role == "user"]
    if not users:
        raise HTTPException(400, "At least one user message required")
    if len(messages) == 1:
        return users[-1].strip()
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)


def _resolve_force_model(model: str) -> Optional[str]:
    if model in ("auto", "neuralrouter-auto", "default", "gpt-4", "gpt-4o"):
        return None
    if model in REGISTRY:
        return model
    for mid, meta in REGISTRY.items():
        if meta.get("api_model_string") == model:
            return mid
    raise HTTPException(
        400,
        f"Unknown model '{model}'. Use 'auto' or: {', '.join(REGISTRY.keys())}",
    )


async def _execute_chat(
    message: str,
    force_model: Optional[str],
    auth: AuthContext,
    search_mode: str = "auto",
) -> tuple:
    request_id = f"req_{uuid.uuid4().hex[:16]}"

    if auth.user_id:
        try:
            check_quota(auth.user_id, auth.plan_id)
        except QuotaExceededError as exc:
            raise HTTPException(
                402,
                detail={
                    "error": "quota_exceeded",
                    "plan": exc.plan_id,
                    "tokens_used": exc.used,
                    "tokens_limit": exc.limit,
                    "upgrade_url": "/web/dashboard/",
                },
            ) from exc

    if force_model:
        manual_expert(force_model)

    async with ConcurrencyGuard(auth.client_label):
        result = await run_chat(message, force_model, search_mode=search_mode)  # type: ignore[arg-type]

    row_id = log_interaction(
        query=message,
        model_response=result.answer,
        model_used=result.brain_used,
        expert_id=result.expert_id,
        router_confidence=result.confidence,
        collaborative=result.collaborative,
        all_experts_used=result.all_experts_used,
        user_behavior={"response_time_s": result.response_time_s},
        tokens_used=result.tokens,
        sub_model_responses=result.sub_model_responses,
        tenant_id=auth.user_id,
        training_opt_in=auth.training_opt_in if auth.user_id else False,
    )

    if auth.user_id:
        record_usage(
            user_id=auth.user_id,
            api_key_id=auth.api_key_id,
            request_id=request_id,
            model_used=result.brain_used,
            expert_id=result.expert_id,
            tokens_input=result.prompt_tokens or 0,
            tokens_output=result.completion_tokens or 0,
            latency_ms=int(result.response_time_s * 1000),
        )

    return result, row_id


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "saas_db": saas_db_enabled(),
        "models_loaded": list(REGISTRY.keys()),
        "load": active_users_summary(),
        "provider_circuits": balancer.status(),
    }


@app.get("/")
async def root():
    return {
        "product": "Aksh by Aitotech",
        "model": "Omni",
        "docs": "/docs",
        "roadmap": "/docs/AKSH_ROADMAP.md",
        "dashboard": "/web/dashboard/",
        "chat": "/web/chat.html",
    }


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    rate_limit(request, auth)
    result, row_id = await _execute_chat(body.message, body.force_model, auth, body.search or "auto")
    return ChatResponse(
        row_id=row_id,
        answer=result.answer,
        brain_used=result.brain_used,
        all_experts_used=result.all_experts_used,
        collaborative=result.collaborative,
        confidence=result.confidence,
        tokens_used=result.tokens,
        web_search_used=result.web_search_used,
        omni_controller=result.omni_plan,
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: OpenAIChatRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    """OpenAI-compatible endpoint for Cursor, Codex, Continue, etc."""
    rate_limit(request, auth)

    if body.stream:
        raise HTTPException(
            501,
            "Streaming not supported yet. Set stream=false.",
        )

    message = _messages_to_query(body.messages)
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(400, f"Message too long (max {MAX_MESSAGE_CHARS} chars)")

    force = _resolve_force_model(body.model)
    result, _row_id = await _execute_chat(message, force, auth, body.search or "auto")

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model if body.model != "auto" else result.brain_used,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens or 0,
            "completion_tokens": result.completion_tokens or 0,
            "total_tokens": result.tokens or 0,
        },
        "system_fingerprint": f"neuralrouter-{result.brain_used}",
    }


@app.get("/v1/models")
async def list_models(
    request: Request,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    rate_limit(request, auth)
    created = int(time.time())
    data = [
        {
            "id": "auto",
            "object": "model",
            "created": created,
            "owned_by": "aitotech",
        }
    ]
    for mid, meta in REGISTRY.items():
        data.append(
            {
                "id": mid,
                "object": "model",
                "created": created,
                "owned_by": meta.get("provider", "aitotech"),
            }
        )
    return {"object": "list", "data": data}


@app.post("/v1/feedback")
async def feedback(
    request: Request,
    body: FeedbackRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    rate_limit(request, auth)
    ok = record_feedback(
        row_id=body.row_id,
        thumbs=body.thumbs,
        retry=body.retry,
        time_spent_s=body.time_spent_s,
    )
    if not ok:
        raise HTTPException(404, "row_id not found in raw log")
    return {"status": "recorded", "row_id": body.row_id}


@app.get("/v1/router/models")
async def list_models_detail(
    request: Request,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    rate_limit(request, auth)
    return {
        "models": [
            {
                "id": m["model_id"],
                "name": m["display_name"],
                "domains": m.get("specialty_domains", []),
                "context_window": m.get("context_window"),
            }
            for m in REGISTRY.values()
        ]
    }


@app.post("/saas/v1/stripe/webhook")
async def stripe_webhook_endpoint(request: Request):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    result = handle_webhook(payload, sig)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "webhook_failed"))
    return result


@app.get("/admin/omni/stats")
async def admin_omni_stats(
    request: Request,
    auth: Annotated[AuthContext, Depends(verify_auth)],
    x_omni_admin_key: Annotated[str | None, Header()] = None,
):
    rate_limit(request, auth)
    if not verify_admin_key(x_omni_admin_key):
        raise HTTPException(403, "Invalid or missing X-Omni-Admin-Key")
    return vault_stats()


@app.get("/admin/system/status")
async def admin_system_status(
    request: Request,
    auth: Annotated[AuthContext, Depends(verify_auth)],
    x_omni_admin_key: Annotated[str | None, Header()] = None,
):
    rate_limit(request, auth)
    if not verify_admin_key(x_omni_admin_key):
        raise HTTPException(403, "Invalid or missing X-Omni-Admin-Key")
    return {
        "load": active_users_summary(),
        "provider_circuits": balancer.status(),
        "vault": vault_stats(),
        "saas_db": saas_db_enabled(),
    }
