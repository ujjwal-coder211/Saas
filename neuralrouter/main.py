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

import json

from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
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
from neuralrouter.omni_brain.loader import active_brain_summary
from neuralrouter.search import search_status
from saas.billing.usage import QuotaExceededError, check_quota, record_usage
from saas.billing.stripe_webhooks import handle_webhook
from saas.api.routes import router as saas_router
from saas.api.skills import router as skills_router
from saas.api.threads import router as threads_router, load_thread_history, save_chat_turn
from saas.api.projects import router as projects_router
from saas.db.connection import saas_db_enabled
from neuralrouter.chat_service import PUBLIC_MODEL_ID
from neuralrouter.project_context import enrich_message_with_project, resolve_agent_root
from neuralrouter.work_modes import WorkMode

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
app.include_router(threads_router)
app.include_router(projects_router)

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
    thread_id: Optional[str] = None
    project_id: Optional[str] = None
    work_mode: WorkMode = "auto"
    search: Optional[Literal["auto", "on", "off"]] = "auto"
    file_context: Optional[str] = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    rules: Optional[str] = Field(default=None, max_length=8000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class ChatResponse(BaseModel):
    row_id: str
    answer: str
    brain_used: str = PUBLIC_MODEL_ID
    powered_by: str = "omni"
    thread_id: Optional[str] = None
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
    work_mode: WorkMode = "auto"


class FeedbackRequest(BaseModel):
    row_id: str
    thumbs: Optional[Literal["up", "down"]] = None
    retry: Optional[bool] = None
    time_spent_s: Optional[float] = Field(None, ge=0, le=86400)


class AgentRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    file_context: str = Field(default="", max_length=MAX_MESSAGE_CHARS)
    rules: str = Field(default="", max_length=8000)
    project_id: Optional[str] = None
    work_mode: WorkMode = "auto"
    project_root: Optional[str] = Field(
        default=None,
        description="Optional sandbox root path on server (enterprise on-prem only)",
    )


def _messages_to_query(messages: list[OpenAIMessage]) -> str:
    users = [m.content for m in messages if m.role == "user"]
    if not users:
        raise HTTPException(400, "At least one user message required")
    if len(messages) == 1:
        return users[-1].strip()
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)


def _resolve_force_model(model: str) -> Optional[str]:
    if model in (
        "auto",
        "omni",
        "aksh-omni",
        "neuralrouter-auto",
        "default",
        "gpt-4",
        "gpt-4o",
    ):
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
    file_context: str | None = None,
    rules: str | None = None,
    thread_id: str | None = None,
    project_id: str | None = None,
    work_mode: WorkMode = "auto",
) -> tuple:
    request_id = f"req_{uuid.uuid4().hex[:16]}"

    if project_id and auth.user_id and saas_db_enabled():
        _assert_project_access(project_id, auth.user_id)

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

    history = None
    if thread_id and auth.user_id and saas_db_enabled():
        try:
            history = load_thread_history(thread_id, auth.user_id)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Failed to load thread history")

    async with ConcurrencyGuard(auth.client_label):
        result = await run_chat(
            message,
            force_model,
            search_mode=search_mode,  # type: ignore[arg-type]
            file_context=file_context,
            rules=rules,
            history=history,
            work_mode=work_mode,
            user_id=auth.user_id,
            project_id=project_id,
        )

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
            model_used=PUBLIC_MODEL_ID,
            expert_id=result.expert_id,
            tokens_input=result.prompt_tokens or 0,
            tokens_output=result.completion_tokens or 0,
            latency_ms=int(result.response_time_s * 1000),
        )

    if thread_id and auth.user_id and saas_db_enabled():
        try:
            save_chat_turn(
                thread_id,
                auth.user_id,
                message,
                result.answer,
                row_id=row_id,
                tokens=result.tokens or 0,
            )
        except Exception:
            logger.exception("Failed to save thread messages")

    return result, row_id


def _assert_project_access(project_id: str, user_id: str) -> None:
    from sqlalchemy import text

    from saas.db.connection import db_session

    with db_session() as session:
        row = session.execute(
            text("SELECT id FROM projects WHERE id = :id AND user_id = :uid"),
            {"id": project_id, "uid": user_id},
        ).first()
    if not row:
        raise HTTPException(404, "Project not found")


@app.get("/health")
async def health():
    brain = active_brain_summary()
    search = search_status()
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "product": "Aksh by Aitotech",
        "model": "Omni",
        "saas_db": saas_db_enabled(),
        "models_loaded": list(REGISTRY.keys()),
        "brain": {
            "active_version_id": brain.get("version_id"),
            "label": brain.get("label"),
            "type": brain.get("type"),
            "fallback": brain.get("fallback", False),
        },
        "search": search,
        "load": active_users_summary(),
        "provider_circuits": balancer.status(),
    }


@app.get("/")
async def root():
    return RedirectResponse(url="/web/index.html")


@app.get("/api")
async def api_info():
    return {
        "product": "Aksh by Aitotech",
        "model": PUBLIC_MODEL_ID,
        "docs": "/docs",
        "user_docs": "/web/docs/",
        "landing": "/web/index.html",
        "dashboard": "/web/dashboard/",
        "studio": "/web/studio/",
        "chat": "/web/chat.html",
    }


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    rate_limit(request, auth)
    result, row_id = await _execute_chat(
        body.message,
        body.force_model,
        auth,
        body.search or "auto",
        file_context=body.file_context,
        rules=body.rules,
        thread_id=body.thread_id,
        project_id=body.project_id,
        work_mode=body.work_mode,
    )
    return ChatResponse(
        row_id=row_id,
        answer=result.answer,
        brain_used=PUBLIC_MODEL_ID,
        powered_by="omni",
        thread_id=body.thread_id,
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
        message = _messages_to_query(body.messages)
        if len(message) > MAX_MESSAGE_CHARS:
            raise HTTPException(400, f"Message too long (max {MAX_MESSAGE_CHARS} chars)")
        force = _resolve_force_model(body.model)

        async def event_stream():
            result, _row_id = await _execute_chat(
                message,
                force,
                auth,
                body.search or "auto",
                work_mode=body.work_mode,
            )
            payload = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": PUBLIC_MODEL_ID,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": result.answer},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(payload)}\n\n"
            done = {
                "id": payload["id"],
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(done)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    message = _messages_to_query(body.messages)
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(400, f"Message too long (max {MAX_MESSAGE_CHARS} chars)")

    force = _resolve_force_model(body.model)
    result, _row_id = await _execute_chat(
        message,
        force,
        auth,
        body.search or "auto",
        work_mode=body.work_mode,
    )

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": PUBLIC_MODEL_ID,
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
        "system_fingerprint": f"aksh-omni-{result.omni_plan.get('brain_version_id') if result.omni_plan else 'v0'}",
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
            "id": PUBLIC_MODEL_ID,
            "object": "model",
            "created": created,
            "owned_by": "aitotech",
        },
        {
            "id": "auto",
            "object": "model",
            "created": created,
            "owned_by": "aitotech",
        },
    ]
    return {"object": "list", "data": data}


@app.get("/v1/omni/brain")
async def omni_brain_public(
    request: Request,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    """Read-only active Omni brain info for authenticated users."""
    rate_limit(request, auth)
    from omni_training.brain_registry import load_registry

    reg = load_registry()
    active = active_brain_summary()
    return {
        "active_version_id": reg.get("active_version_id"),
        "active": active,
        "updated_at": reg.get("updated_at"),
    }


@app.post("/v1/agent/run")
async def agent_run(
    request: Request,
    body: AgentRunRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    """Aksh Agent — plan → tools → synthesize on cloud project or enterprise path."""
    rate_limit(request, auth)
    from pathlib import Path

    from neuralrouter.agent.agent_loop import run_agent_loop
    from neuralrouter.model_clients import call_model, provider_configured

    if not provider_configured():
        raise HTTPException(
            503,
            "Omni Agent needs OPENROUTER_API_KEY (or other provider keys) in .env",
        )

    project_root: Path | None = None
    rules = body.rules
    file_context = body.file_context

    if body.project_id:
        if not auth.user_id or not saas_db_enabled():
            raise HTTPException(401, "Cloud agent requires SaaS account and DATABASE_URL")
        _assert_project_access(body.project_id, auth.user_id)
        project_root = resolve_agent_root(auth.user_id, body.project_id)
        enriched, rules = enrich_message_with_project(
            body.task,
            auth.user_id,
            body.project_id,
            rules=body.rules or None,
        )
        if not file_context:
            file_context = enriched
    elif body.project_root:
        project_root = Path(body.project_root).resolve()

    async def llm_plan(messages: list[dict]) -> str:
        text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        result = await call_model(
            text,
            "qwen",
            system_prompt="You are Aksh Agent powered by Omni. Follow work mode scope strictly.",
        )
        return result.get("content", "")

    try:
        result = await run_agent_loop(
            body.task,
            file_context=file_context,
            rules=rules,
            project_root=project_root,
            work_mode=body.work_mode,
            llm_plan=llm_plan,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "answer": result.answer,
        "tools_used": result.tools_used,
        "work_mode": result.work_mode,
        "scope_summary": result.scope_summary,
        "project_id": body.project_id,
        "steps": [
            {
                "step": s.step,
                "kind": s.kind,
                "content": s.content[:2000],
                "tool_result": s.tool_result,
            }
            for s in result.steps
        ],
    }


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


@app.get("/admin/omni/brain")
async def admin_omni_brain(
    request: Request,
    auth: Annotated[AuthContext, Depends(verify_auth)],
    x_omni_admin_key: Annotated[str | None, Header()] = None,
):
    """List Omni brain versions — active, candidates, archived."""
    rate_limit(request, auth)
    if not verify_admin_key(x_omni_admin_key):
        raise HTTPException(403, "Invalid or missing X-Omni-Admin-Key")
    from omni_training.brain_registry import get_active_brain, list_versions, load_registry

    reg = load_registry()
    return {
        "active_version_id": reg.get("active_version_id"),
        "active": get_active_brain(),
        "versions": list_versions(),
    }


class PromoteBrainRequest(BaseModel):
    version_id: str
    approve: bool = True
    force: bool = False


@app.post("/admin/omni/brain/promote")
async def admin_promote_brain(
    request: Request,
    body: PromoteBrainRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
    x_omni_admin_key: Annotated[str | None, Header()] = None,
):
    """Hot-replace active Omni main brain with trained candidate."""
    rate_limit(request, auth)
    if not verify_admin_key(x_omni_admin_key):
        raise HTTPException(403, "Invalid or missing X-Omni-Admin-Key")
    from omni_training.brain_registry import promote, update_metrics

    try:
        if body.approve:
            update_metrics(body.version_id, {"manual_approved": True})
        result = promote(body.version_id, force=body.force)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
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
