"""Aksh Skills / MCP registration — feeds Sarva training pipeline."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from neuralrouter.auth import verify_auth
from saas.auth.context import AuthContext

router = APIRouter(prefix="/saas/v1/skills", tags=["aksh-skills"])


class RegisterSkillRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    skill_type: Literal["skill", "mcp", "plugin"] = "skill"
    local_path: Optional[str] = Field(None, description="Server-visible path to skill folder")
    git_url: Optional[str] = Field(None, description="Public git repo to clone and ingest")


@router.post("/register")
async def register_skill(
    body: RegisterSkillRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    """
    Add Skill / MCP — codebase scanned → Sarva training vault.
    Requires tenant API key. User should enable training_opt_in for full pipeline.
    """
    if not auth.user_id:
        raise HTTPException(400, "SaaS tenant required")

    from sarva_training.skill_ingest import ingest_from_git_url, ingest_skill_path

    try:
        if body.git_url:
            result = ingest_from_git_url(auth.user_id, body.name, body.git_url)
        elif body.local_path:
            result = ingest_skill_path(
                tenant_id=auth.user_id,
                skill_name=body.name,
                source_path=body.local_path,
                skill_type=body.skill_type,
            )
        else:
            raise HTTPException(400, "Provide local_path or git_url")
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Ingest failed: {exc}") from exc

    return {
        "status": "ingested",
        "message": "Skill codebase added to Sarva training queue. Run curate.py → build_dataset.py.",
        **result,
    }


@router.get("/list")
async def list_skills(auth: Annotated[AuthContext, Depends(verify_auth)]):
    from sarva_training.skill_ingest import SKILLS_REGISTRY_PATH
    import json

    if not SKILLS_REGISTRY_PATH.exists():
        return {"skills": []}

    skills = []
    with open(SKILLS_REGISTRY_PATH, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if auth.user_id and row.get("tenant_id") != auth.user_id:
                continue
            skills.append(row)
    return {"skills": skills}
