"""Per-user API key generation and verification (hashed storage)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from sqlalchemy import text

from saas.billing.plans import get_plan
from saas.db.connection import db_session, saas_db_enabled


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_raw_key() -> str:
    return f"sk_live_{secrets.token_urlsafe(32)}"


def create_api_key(user_id: str, name: str = "default") -> dict[str, str]:
    raw = generate_raw_key()
    prefix = raw[:16] + "…"
    key_hash = _hash_key(raw)

    with db_session() as session:
        session.execute(
            text(
                """
                INSERT INTO api_keys (user_id, key_prefix, key_hash, name)
                VALUES (:uid, :prefix, :key_hash, :name)
                """
            ),
            {"uid": user_id, "prefix": prefix, "key_hash": key_hash, "name": name},
        )

    return {"api_key": raw, "key_prefix": prefix, "name": name}


def verify_db_api_key(raw_key: str) -> dict[str, Any] | None:
    if not saas_db_enabled():
        return None

    key_hash = _hash_key(raw_key)
    with db_session() as session:
        row = session.execute(
            text(
                """
                SELECT k.id, k.user_id, k.key_prefix, u.email, u.plan_id, u.training_opt_in
                FROM api_keys k
                JOIN users u ON u.id = k.user_id
                WHERE k.key_hash = :kh AND k.revoked_at IS NULL
                """
            ),
            {"kh": key_hash},
        ).fetchone()

    if not row:
        return None

    plan = get_plan(row[4])
    return {
        "api_key_id": str(row[0]),
        "user_id": str(row[1]),
        "key_prefix": row[2],
        "email": row[3],
        "plan_id": row[4],
        "training_opt_in": bool(row[5]),
        "rate_limit_per_minute": plan.rate_limit_per_minute,
        "max_concurrent": plan.max_concurrent,
    }


def list_user_keys(user_id: str) -> list[dict]:
    with db_session() as session:
        rows = session.execute(
            text(
                """
                SELECT id, key_prefix, name, revoked_at, created_at
                FROM api_keys WHERE user_id = :uid ORDER BY created_at DESC
                """
            ),
            {"uid": user_id},
        ).fetchall()

    return [
        {
            "id": str(r[0]),
            "key_prefix": r[1],
            "name": r[2],
            "revoked": r[3] is not None,
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


def revoke_api_key(user_id: str, key_id: str) -> bool:
    with db_session() as session:
        result = session.execute(
            text(
                """
                UPDATE api_keys SET revoked_at = NOW()
                WHERE id = :kid AND user_id = :uid AND revoked_at IS NULL
                """
            ),
            {"kid": key_id, "uid": user_id},
        )
        return result.rowcount > 0


def create_user_with_key(email: str, plan_id: str = "free") -> dict:
    raw = generate_raw_key()
    prefix = raw[:16] + "…"
    key_hash = _hash_key(raw)

    with db_session() as session:
        user_row = session.execute(
            text(
                """
                INSERT INTO users (email, plan_id)
                VALUES (:email, :plan_id)
                RETURNING id
                """
            ),
            {"email": email, "plan_id": plan_id},
        ).fetchone()
        user_id = str(user_row[0])
        session.execute(
            text(
                """
                INSERT INTO api_keys (user_id, key_prefix, key_hash, name)
                VALUES (:uid, :prefix, :key_hash, 'default')
                """
            ),
            {"uid": user_id, "prefix": prefix, "key_hash": key_hash},
        )

    return {
        "user_id": user_id,
        "email": email,
        "plan_id": plan_id,
        "api_key": raw,
        "key_prefix": prefix,
    }
