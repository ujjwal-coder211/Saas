"""Token usage recording and quota checks — SaaS billing source of truth."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text

from saas.billing.plans import estimate_cost_usd, get_plan
from saas.db.connection import db_session, saas_db_enabled

logger = logging.getLogger(__name__)


def _year_month(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")


def check_quota(user_id: str, plan_id: str, extra_tokens: int = 0) -> None:
    """Raise ValueError if user would exceed monthly token cap."""
    if not saas_db_enabled():
        return

    plan = get_plan(plan_id)
    if plan.monthly_tokens is None:
        return

    with db_session() as session:
        row = session.execute(
            text(
                """
                SELECT tokens_total FROM usage_monthly
                WHERE user_id = :uid AND year_month = :ym
                """
            ),
            {"uid": user_id, "ym": _year_month()},
        ).fetchone()

    used = int(row[0]) if row else 0
    if used + extra_tokens > plan.monthly_tokens:
        raise QuotaExceededError(
            plan_id=plan_id,
            used=used,
            limit=plan.monthly_tokens,
        )


class QuotaExceededError(Exception):
    def __init__(self, plan_id: str, used: int, limit: int):
        self.plan_id = plan_id
        self.used = used
        self.limit = limit
        super().__init__(f"Monthly token limit exceeded ({used}/{limit}) on plan {plan_id}")


def record_usage(
    *,
    user_id: str,
    api_key_id: str | None,
    request_id: str,
    model_used: str,
    expert_id: str,
    tokens_input: int,
    tokens_output: int,
    latency_ms: int | None = None,
) -> dict:
    """Insert usage_events + upsert usage_monthly."""
    if not saas_db_enabled():
        return {"recorded": False, "reason": "database_disabled"}

    tokens_total = max(0, tokens_input) + max(0, tokens_output)
    cost = estimate_cost_usd(tokens_total)
    ym = _year_month()

    with db_session() as session:
        session.execute(
            text(
                """
                INSERT INTO usage_events (
                    user_id, api_key_id, request_id, model_used, expert_id,
                    tokens_input, tokens_output, tokens_total, latency_ms, estimated_cost_usd
                ) VALUES (
                    :user_id, :api_key_id, :request_id, :model_used, :expert_id,
                    :tokens_input, :tokens_output, :tokens_total, :latency_ms, :cost
                )
                """
            ),
            {
                "user_id": user_id,
                "api_key_id": api_key_id,
                "request_id": request_id,
                "model_used": model_used,
                "expert_id": expert_id,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "tokens_total": tokens_total,
                "latency_ms": latency_ms,
                "cost": cost,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO usage_monthly (user_id, year_month, tokens_total, requests_count, estimated_cost_usd)
                VALUES (:uid, :ym, :tokens, 1, :cost)
                ON CONFLICT (user_id, year_month) DO UPDATE SET
                    tokens_total = usage_monthly.tokens_total + EXCLUDED.tokens_total,
                    requests_count = usage_monthly.requests_count + 1,
                    estimated_cost_usd = usage_monthly.estimated_cost_usd + EXCLUDED.estimated_cost_usd
                """
            ),
            {"uid": user_id, "ym": ym, "tokens": tokens_total, "cost": cost},
        )

    return {
        "recorded": True,
        "tokens_total": tokens_total,
        "estimated_cost_usd": cost,
        "year_month": ym,
    }


def get_usage_summary(user_id: str) -> dict:
    if not saas_db_enabled():
        return {"enabled": False}

    ym = _year_month()
    with db_session() as session:
        monthly = session.execute(
            text(
                """
                SELECT tokens_total, requests_count, estimated_cost_usd
                FROM usage_monthly WHERE user_id = :uid AND year_month = :ym
                """
            ),
            {"uid": user_id, "ym": ym},
        ).fetchone()

        user = session.execute(
            text("SELECT email, plan_id, training_opt_in, created_at FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).fetchone()

        recent = session.execute(
            text(
                """
                SELECT request_id, model_used, tokens_total, created_at
                FROM usage_events WHERE user_id = :uid
                ORDER BY created_at DESC LIMIT 20
                """
            ),
            {"uid": user_id},
        ).fetchall()

    plan = get_plan(user[1] if user else "free")
    used = int(monthly[0]) if monthly else 0

    return {
        "enabled": True,
        "email": user[0] if user else None,
        "plan_id": user[1] if user else "free",
        "plan_name": plan.name,
        "training_opt_in": bool(user[2]) if user else False,
        "month": ym,
        "tokens_used": used,
        "tokens_limit": plan.monthly_tokens,
        "requests_count": int(monthly[1]) if monthly else 0,
        "estimated_cost_usd": float(monthly[2]) if monthly else 0.0,
        "recent_events": [
            {
                "request_id": r[0],
                "model_used": r[1],
                "tokens_total": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
            }
            for r in recent
        ],
    }
