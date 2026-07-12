"""Cursor parity API routes — inline, tab, composer, terminal, git, MCP, jobs, review."""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from neuralrouter.auth import verify_auth
from neuralrouter.project_access import assert_project_access
from neuralrouter.project_context import resolve_agent_root
from saas.auth.context import AuthContext
from saas.db.connection import saas_db_enabled

router = APIRouter(prefix="/v1", tags=["parity"])


class InlineEditRequest(BaseModel):
    project_id: Optional[str] = None
    file_path: str = Field(..., min_length=1)
    full_content: str = Field(default="", max_length=512000)
    selection: str = Field(..., max_length=50000)
    instruction: str = Field(..., min_length=1, max_length=4000)
    language: str = "plaintext"


class TabCompleteRequest(BaseModel):
    project_id: Optional[str] = None
    file_path: str = Field(..., min_length=1)
    content: str = Field(default="", max_length=512000)
    prefix: str = Field(default="", max_length=500)
    line: int = Field(default=1, ge=1)
    column: int = Field(default=1, ge=1)


class ComposerRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=8000)
    project_id: str
    rules: str = ""


class TerminalRequest(BaseModel):
    project_id: str
    command: str = Field(..., min_length=1, max_length=2000)


class GitCommitRequest(BaseModel):
    project_id: str
    message: str = Field(..., min_length=1, max_length=500)


class ReviewRequest(BaseModel):
    project_id: str
    focus: str = "bugs and security"


class BackgroundAgentRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=8000)
    project_id: Optional[str] = None
    work_mode: str = "auto"


def _require_project(auth: AuthContext, project_id: str):
    if not auth.user_id or not saas_db_enabled():
        raise HTTPException(401, "SaaS account + DATABASE_URL required")
    assert_project_access(project_id, auth.user_id)
    return resolve_agent_root(auth.user_id, project_id)


@router.post("/inline/edit")
async def inline_edit_endpoint(
    body: InlineEditRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.inline import inline_edit

    if body.project_id:
        _require_project(auth, body.project_id)
    try:
        result = await inline_edit(
            file_path=body.file_path,
            full_content=body.full_content,
            selection=body.selection,
            instruction=body.instruction,
            language=body.language,
        )
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    return result


@router.post("/complete/tab")
async def tab_complete_endpoint(
    body: TabCompleteRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.inline import tab_complete

    if body.project_id:
        _require_project(auth, body.project_id)
    return await tab_complete(
        file_path=body.file_path,
        content=body.content,
        prefix=body.prefix,
        line=body.line,
        column=body.column,
    )


@router.post("/composer/run")
async def composer_run(
    body: ComposerRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.composer import run_composer

    if not auth.user_id:
        raise HTTPException(401, "SaaS API key required")
    assert_project_access(body.project_id, auth.user_id)
    try:
        result = await run_composer(
            body.task,
            auth.user_id,
            body.project_id,
            rules=body.rules,
        )
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "answer": result.answer,
        "files_changed": result.files_changed,
        "plan": result.plan,
    }


@router.post("/terminal/run")
async def terminal_run(
    body: TerminalRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.terminal import run_terminal

    root = _require_project(auth, body.project_id)
    return run_terminal(root, body.command)


@router.get("/git/status")
async def git_status_endpoint(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.git import git_status

    root = _require_project(auth, project_id)
    return git_status(root)


@router.get("/git/diff")
async def git_diff_endpoint(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
    path: str = ".",
):
    from neuralrouter.parity.git import git_diff

    root = _require_project(auth, project_id)
    return git_diff(root, path)


@router.post("/git/commit")
async def git_commit_endpoint(
    body: GitCommitRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.git import git_commit

    root = _require_project(auth, body.project_id)
    return git_commit(root, body.message)


@router.get("/mcp/tools")
async def mcp_list_tools(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.mcp import list_mcp_tools

    if not auth.user_id:
        raise HTTPException(401, "SaaS API key required")
    assert_project_access(project_id, auth.user_id)
    return {"tools": list_mcp_tools(auth.user_id, project_id)}


@router.post("/review/code")
async def review_code(
    body: ReviewRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.review import review_project

    if not auth.user_id:
        raise HTTPException(401, "SaaS API key required")
    root = _require_project(auth, body.project_id)
    return await review_project(auth.user_id, body.project_id, root, focus=body.focus)


@router.post("/jobs/agent")
async def background_agent(
    body: BackgroundAgentRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.agent.agent_loop import run_agent_loop
    from neuralrouter.model_clients import call_model
    from neuralrouter.parity.jobs import create_job, run_job_async

    job_id = create_job(body.task, auth.user_id)
    root = None
    if body.project_id:
        root = _require_project(auth, body.project_id)

    async def llm_plan(messages: list[dict]) -> str:
        text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        result = await call_model(text, "qwen", system_prompt="You are Sarva Agent.")
        return result.get("content", "")

    async def work():
        result = await run_agent_loop(
            body.task,
            project_root=root,
            work_mode=body.work_mode,  # type: ignore[arg-type]
            llm_plan=llm_plan,
        )
        return {"answer": result.answer, "tools_used": result.tools_used}

    asyncio.create_task(run_job_async(job_id, work))
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.jobs import get_job

    rec = get_job(job_id, auth.user_id)
    if not rec:
        raise HTTPException(404, "Job not found")
    return rec


@router.get("/jobs")
async def list_job_status(
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    from neuralrouter.parity.jobs import list_jobs

    return {"jobs": list_jobs(auth.user_id)}
