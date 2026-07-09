"""Sarva Memory — per-user chat threads API (Routely persistent memory)."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from neuralrouter.auth import verify_auth
from saas.auth.context import AuthContext
from saas.db.connection import db_session, saas_db_enabled

router = APIRouter(prefix="/saas/v1/threads", tags=["threads"])

MAX_HISTORY = 40


class CreateThreadRequest(BaseModel):
    title: str = Field(default="New chat", max_length=200)
    project_id: Optional[str] = None


class AppendMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=32000)
    tokens: int = Field(default=0, ge=0)
    row_id: Optional[str] = None


def _require_user(auth: AuthContext) -> str:
    if not saas_db_enabled():
        raise HTTPException(503, "DATABASE_URL required for Sarva Memory threads")
    if not auth.user_id:
        raise HTTPException(401, "Sign up and use a SaaS API key for persistent memory")
    return auth.user_id


def _verify_thread(session, thread_id: str, user_id: str) -> None:
    row = session.execute(
        text("SELECT id FROM chat_threads WHERE id = :id AND user_id = :uid"),
        {"id": thread_id, "uid": user_id},
    ).first()
    if not row:
        raise HTTPException(404, "Thread not found")


@router.get("")
async def list_threads(auth: Annotated[AuthContext, Depends(verify_auth)]):
    user_id = _require_user(auth)
    with db_session() as session:
        rows = session.execute(
            text(
                """
                SELECT id, title, project_id, summary, created_at, updated_at
                FROM chat_threads
                WHERE user_id = :uid
                ORDER BY updated_at DESC
                LIMIT 100
                """
            ),
            {"uid": user_id},
        ).mappings().all()
    return {"threads": [dict(r) for r in rows]}


@router.post("")
async def create_thread(
    body: CreateThreadRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    thread_id = str(uuid.uuid4())
    with db_session() as session:
        session.execute(
            text(
                """
                INSERT INTO chat_threads (id, user_id, project_id, title)
                VALUES (:id, :uid, :pid, :title)
                """
            ),
            {
                "id": thread_id,
                "uid": user_id,
                "pid": body.project_id,
                "title": body.title.strip() or "New chat",
            },
        )
    return {"id": thread_id, "title": body.title}


@router.get("/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    with db_session() as session:
        _verify_thread(session, thread_id, user_id)
        rows = session.execute(
            text(
                """
                SELECT id, role, content, tokens, row_id, created_at
                FROM chat_messages
                WHERE thread_id = :tid
                ORDER BY created_at ASC
                LIMIT :lim
                """
            ),
            {"tid": thread_id, "lim": MAX_HISTORY},
        ).mappings().all()
    return {"thread_id": thread_id, "messages": [dict(r) for r in rows]}


@router.post("/{thread_id}/messages")
async def append_message(
    thread_id: str,
    body: AppendMessageRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    msg_id = str(uuid.uuid4())
    with db_session() as session:
        _verify_thread(session, thread_id, user_id)
        session.execute(
            text(
                """
                INSERT INTO chat_messages (id, thread_id, role, content, tokens, row_id)
                VALUES (:id, :tid, :role, :content, :tokens, :row_id)
                """
            ),
            {
                "id": msg_id,
                "tid": thread_id,
                "role": body.role,
                "content": body.content,
                "tokens": body.tokens,
                "row_id": body.row_id,
            },
        )
        session.execute(
            text("UPDATE chat_threads SET updated_at = NOW() WHERE id = :tid"),
            {"tid": thread_id},
        )
    return {"id": msg_id, "status": "saved"}


def load_thread_history(thread_id: str, user_id: str, limit: int = 20) -> list[dict]:
    """Load recent messages for Sarva context injection."""
    with db_session() as session:
        _verify_thread(session, thread_id, user_id)
        rows = session.execute(
            text(
                """
                SELECT role, content FROM chat_messages
                WHERE thread_id = :tid
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"tid": thread_id, "lim": limit},
        ).mappings().all()
    return list(reversed([dict(r) for r in rows]))


def save_chat_turn(
    thread_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
    row_id: str | None = None,
    tokens: int = 0,
) -> None:
    with db_session() as session:
        _verify_thread(session, thread_id, user_id)
        session.execute(
            text(
                """
                INSERT INTO chat_messages (thread_id, role, content)
                VALUES (:tid, 'user', :content)
                """
            ),
            {"tid": thread_id, "content": user_message},
        )
        session.execute(
            text(
                """
                INSERT INTO chat_messages (thread_id, role, content, tokens, row_id)
                VALUES (:tid, 'assistant', :content, :tokens, :row_id)
                """
            ),
            {
                "tid": thread_id,
                "content": assistant_message,
                "tokens": tokens,
                "row_id": row_id,
            },
        )
        title_seed = user_message.strip()[:80]
        session.execute(
            text(
                """
                UPDATE chat_threads
                SET updated_at = NOW(),
                    title = CASE WHEN title = 'New chat' THEN :title ELSE title END
                WHERE id = :tid
                """
            ),
            {"tid": thread_id, "title": title_seed or "New chat"},
        )
