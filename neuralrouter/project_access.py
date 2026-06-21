"""Shared project access checks."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from saas.db.connection import db_session, saas_db_enabled


def assert_project_access(project_id: str, user_id: str) -> None:
    if not saas_db_enabled():
        raise HTTPException(503, "DATABASE_URL required")
    with db_session() as session:
        row = session.execute(
            text("SELECT id FROM projects WHERE id = :id AND user_id = :uid"),
            {"id": project_id, "uid": user_id},
        ).first()
    if not row:
        raise HTTPException(404, "Project not found")
