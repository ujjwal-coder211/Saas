"""Aksh Cloud Projects — upload, file CRUD."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from neuralrouter.auth import verify_auth
from saas.auth.context import AuthContext
from saas.db.connection import db_session, saas_db_enabled
from saas.storage.projects import (
    delete_project_files,
    ensure_storage,
    import_zip,
    list_files,
    project_root_path,
    read_file,
    write_file,
)
from neuralrouter.deploy.kit import generate_deploy_kit
from neuralrouter.security.scan import scan_project

router = APIRouter(prefix="/saas/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class WriteFileRequest(BaseModel):
    content: str = Field(default="", max_length=512000)


def _require_user(auth: AuthContext) -> str:
    if not saas_db_enabled():
        raise HTTPException(503, "DATABASE_URL required for cloud projects")
    if not auth.user_id:
        raise HTTPException(401, "Sign up and use a SaaS API key for cloud projects")
    return auth.user_id


def _get_project(session, project_id: str, user_id: str):
    row = session.execute(
        text(
            """
            SELECT id, name, storage_prefix, created_at, updated_at
            FROM projects WHERE id = :id AND user_id = :uid
            """
        ),
        {"id": project_id, "uid": user_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


@router.get("")
async def list_projects(auth: Annotated[AuthContext, Depends(verify_auth)]):
    user_id = _require_user(auth)
    with db_session() as session:
        rows = session.execute(
            text(
                """
                SELECT id, name, storage_prefix, created_at, updated_at
                FROM projects WHERE user_id = :uid
                ORDER BY updated_at DESC
                """
            ),
            {"uid": user_id},
        ).mappings().all()
    return {"projects": [dict(r) for r in rows]}


@router.post("")
async def create_project(
    body: CreateProjectRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    ensure_storage()
    project_id = str(uuid.uuid4())
    prefix = f"{user_id}/{project_id}"
    name = body.name.strip()
    with db_session() as session:
        session.execute(
            text(
                """
                INSERT INTO projects (id, user_id, name, storage_prefix)
                VALUES (:id, :uid, :name, :prefix)
                """
            ),
            {"id": project_id, "uid": user_id, "name": name, "prefix": prefix},
        )
    write_file(user_id, project_id, "README.md", f"# {name}\n\nCreated with Aksh Studio.\n")
    write_file(user_id, project_id, ".akshrules", "Be concise. Prefer working code.\n")
    return {"id": project_id, "name": name}


@router.post("/upload")
async def upload_project(
    auth: Annotated[AuthContext, Depends(verify_auth)],
    file: UploadFile = File(...),
    name: Optional[str] = None,
):
    user_id = _require_user(auth)
    raw = await file.read()
    project_name = (name or (file.filename or "upload").replace(".zip", "")).strip() or "upload"
    project_id = str(uuid.uuid4())
    prefix = f"{user_id}/{project_id}"
    try:
        paths = import_zip(user_id, project_id, raw, project_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with db_session() as session:
        session.execute(
            text(
                """
                INSERT INTO projects (id, user_id, name, storage_prefix)
                VALUES (:id, :uid, :name, :prefix)
                """
            ),
            {"id": project_id, "uid": user_id, "name": project_name, "prefix": prefix},
        )
        for path in paths:
            try:
                content = read_file(user_id, project_id, path)
                meta = write_file(user_id, project_id, path, content)
            except Exception:
                meta = {"path": path, "size_bytes": 0, "content_hash": None}
            session.execute(
                text(
                    """
                    INSERT INTO project_files (project_id, path, content_hash, size_bytes)
                    VALUES (:pid, :path, :hash, :size)
                    ON CONFLICT (project_id, path) DO UPDATE
                    SET content_hash = EXCLUDED.content_hash,
                        size_bytes = EXCLUDED.size_bytes,
                        updated_at = NOW()
                    """
                ),
                {
                    "pid": project_id,
                    "path": path,
                    "hash": meta.get("content_hash"),
                    "size": meta.get("size_bytes", 0),
                },
            )
    return {"id": project_id, "name": project_name, "files": paths}


@router.get("/{project_id}/files")
async def get_file_tree(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    with db_session() as session:
        _get_project(session, project_id, user_id)
    return {"project_id": project_id, "files": list_files(user_id, project_id)}


@router.get("/{project_id}/files/{file_path:path}")
async def get_file(
    project_id: str,
    file_path: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    with db_session() as session:
        _get_project(session, project_id, user_id)
    try:
        content = read_file(user_id, project_id, file_path)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"path": file_path, "content": content}


@router.put("/{project_id}/files/{file_path:path}")
async def put_file(
    project_id: str,
    file_path: str,
    body: WriteFileRequest,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    with db_session() as session:
        _get_project(session, project_id, user_id)
    try:
        meta = write_file(user_id, project_id, file_path, body.content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with db_session() as session:
        session.execute(
            text(
                """
                INSERT INTO project_files (project_id, path, content_hash, size_bytes)
                VALUES (:pid, :path, :hash, :size)
                ON CONFLICT (project_id, path) DO UPDATE
                SET content_hash = EXCLUDED.content_hash,
                    size_bytes = EXCLUDED.size_bytes,
                    updated_at = NOW()
                """
            ),
            {
                "pid": project_id,
                "path": meta["path"],
                "hash": meta["content_hash"],
                "size": meta["size_bytes"],
            },
        )
        session.execute(
            text("UPDATE projects SET updated_at = NOW() WHERE id = :id"),
            {"id": project_id},
        )
    return meta


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    user_id = _require_user(auth)
    with db_session() as session:
        _get_project(session, project_id, user_id)
        session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    delete_project_files(user_id, project_id)
    return {"status": "deleted", "id": project_id}


@router.post("/{project_id}/deploy-kit")
async def create_deploy_kit(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    """Generate Dockerfile, compose, DEPLOY.md, and k8s templates in the project."""
    user_id = _require_user(auth)
    with db_session() as session:
        project = _get_project(session, project_id, user_id)
    root = project_root_path(user_id, project_id)
    result = generate_deploy_kit(root, project_name=project["name"])
    with db_session() as session:
        for path in list_files(user_id, project_id):
            try:
                content = read_file(user_id, project_id, path)
                meta = write_file(user_id, project_id, path, content)
            except Exception:
                continue
            session.execute(
                text(
                    """
                    INSERT INTO project_files (project_id, path, content_hash, size_bytes)
                    VALUES (:pid, :path, :hash, :size)
                    ON CONFLICT (project_id, path) DO UPDATE
                    SET content_hash = EXCLUDED.content_hash,
                        size_bytes = EXCLUDED.size_bytes,
                        updated_at = NOW()
                    """
                ),
                {
                    "pid": project_id,
                    "path": path,
                    "hash": meta.get("content_hash"),
                    "size": meta.get("size_bytes", 0),
                },
            )
        session.execute(
            text("UPDATE projects SET updated_at = NOW() WHERE id = :id"),
            {"id": project_id},
        )
    return result


@router.post("/{project_id}/security-scan")
async def security_scan(
    project_id: str,
    auth: Annotated[AuthContext, Depends(verify_auth)],
):
    """Run basic security scan on cloud project files."""
    user_id = _require_user(auth)
    with db_session() as session:
        _get_project(session, project_id, user_id)
    root = project_root_path(user_id, project_id)
    return scan_project(root)
