"""Stripe webhook handlers — activate when STRIPE_WEBHOOK_SECRET is set."""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from saas.db.connection import db_session, saas_db_enabled

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def stripe_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET and saas_db_enabled())


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    if not stripe_enabled():
        return {"ok": False, "error": "stripe_not_configured"}

    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        logger.warning("Stripe webhook verify failed: %s", exc)
        return {"ok": False, "error": "invalid_signature"}

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        _on_checkout_completed(data)
    elif etype == "customer.subscription.updated":
        _on_subscription_updated(data)
    elif etype == "customer.subscription.deleted":
        _on_subscription_deleted(data)

    return {"ok": True, "type": etype}


def _on_checkout_completed(session: dict) -> None:
    customer_id = session.get("customer")
    email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
    plan_id = (session.get("metadata") or {}).get("plan_id", "pro")
    if not email:
        return

    with db_session() as db:
        db.execute(
            text(
                """
                UPDATE users SET plan_id = :plan, stripe_customer_id = :cid, updated_at = NOW()
                WHERE email = :email
                """
            ),
            {"plan": plan_id, "cid": customer_id, "email": email},
        )


def _on_subscription_updated(sub: dict) -> None:
    customer_id = sub.get("customer")
    status = sub.get("status", "active")
    plan_id = (sub.get("metadata") or {}).get("plan_id", "pro")
    period_end = sub.get("current_period_end")

    with db_session() as db:
        user = db.execute(
            text("SELECT id FROM users WHERE stripe_customer_id = :cid"),
            {"cid": customer_id},
        ).fetchone()
        if not user:
            return
        uid = str(user[0])
        db.execute(
            text(
                """
                INSERT INTO subscriptions (user_id, stripe_subscription_id, plan_id, status, current_period_end)
                VALUES (:uid, :sid, :plan, :status, to_timestamp(:end))
                ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                    plan_id = EXCLUDED.plan_id,
                    status = EXCLUDED.status,
                    current_period_end = EXCLUDED.current_period_end
                """
            ),
            {
                "uid": uid,
                "sid": sub.get("id"),
                "plan": plan_id,
                "status": status,
                "end": period_end or 0,
            },
        )
        if status == "active":
            db.execute(
                text("UPDATE users SET plan_id = :plan, updated_at = NOW() WHERE id = :uid"),
                {"plan": plan_id, "uid": uid},
            )


def _on_subscription_deleted(sub: dict) -> None:
    customer_id = sub.get("customer")
    with db_session() as db:
        db.execute(
            text(
                """
                UPDATE users SET plan_id = 'free', updated_at = NOW()
                WHERE stripe_customer_id = :cid
                """
            ),
            {"cid": customer_id},
        )
