"""Billing sanity + Stripe test walkthrough.

Validates the plan/margin math offline (no Stripe or DB needed), simulates the
webhook plan mapping, and prints the exact Stripe CLI steps to test the real
webhook end-to-end.

    python scripts/test_billing.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from saas.billing.plans import (
        BILLING_MARKUP,
        COST_PER_MILLION_TOKENS_USD,
        PLANS,
        estimate_cost_usd,
        get_plan,
    )

    ok = True
    print("=== Plan matrix + illustrative margins ===")
    print(f"(blended provider cost ${COST_PER_MILLION_TOKENS_USD}/1M tok, markup {BILLING_MARKUP}x)\n")
    print(f"{'plan':<8}{'price/mo':>10}{'tokens':>12}{'blended cost':>14}{'margin':>10}")
    for p in PLANS.values():
        toks = p.monthly_tokens
        if toks is None:
            print(f"{p.id:<8}{'usage':>10}{'unlimited':>12}{'passthrough':>14}{'~26%':>10}")
            continue
        cost = round((toks / 1_000_000) * COST_PER_MILLION_TOKENS_USD, 2)
        margin = round(p.price_usd_monthly - cost, 2)
        pct = f"{round(100*margin/p.price_usd_monthly)}%" if p.price_usd_monthly else "n/a"
        print(f"{p.id:<8}{'$'+format(p.price_usd_monthly,'.0f'):>10}{toks:>12,}{'$'+format(cost,'.2f'):>14}{pct:>10}")

    # --- math checks -------------------------------------------------------
    print("\n=== Billing math checks ===")
    c1 = estimate_cost_usd(1_000_000)
    expected = round(COST_PER_MILLION_TOKENS_USD * BILLING_MARKUP, 6)
    print(f"estimate_cost_usd(1M) = {c1}  (expected {expected})")
    ok &= abs(c1 - expected) < 1e-6
    print(f"estimate_cost_usd(0)  = {estimate_cost_usd(0)}  (expected 0.0)")
    ok &= estimate_cost_usd(0) == 0.0

    # --- simulate webhook plan mapping (pure part of _on_checkout_completed) ---
    print("\n=== Simulated checkout.session.completed mapping ===")
    fake_session = {
        "customer": "cus_test123",
        "customer_details": {"email": "buyer@example.com"},
        "metadata": {"plan_id": "pro"},
    }
    email = (fake_session.get("customer_details") or {}).get("email")
    plan_id = (fake_session.get("metadata") or {}).get("plan_id", "pro")
    resolved = get_plan(plan_id)
    print(f"email={email} -> plan_id={plan_id} -> resolved={resolved.name} "
          f"(${resolved.price_usd_monthly}/mo, {resolved.monthly_tokens} tok)")
    ok &= resolved.id == "pro"

    print("\nRESULT:", "PASS ✅" if ok else "FAIL ❌")

    print(
        "\n=== Test the REAL Stripe webhook end-to-end (Stripe CLI) ===\n"
        "1. Install Stripe CLI: https://stripe.com/docs/stripe-cli\n"
        "2. stripe login\n"
        "3. Run your server with STRIPE_SECRET_KEY + DATABASE_URL set (test keys).\n"
        "4. Forward events to your webhook:\n"
        "     stripe listen --forward-to localhost:8000/saas/v1/stripe/webhook\n"
        "   (copy the printed 'whsec_...' into STRIPE_WEBHOOK_SECRET, restart server)\n"
        "5. Trigger a purchase event:\n"
        "     stripe trigger checkout.session.completed\n"
        "6. Verify in the DB that the user's plan_id updated, then confirm quota\n"
        "   enforcement via GET /admin/sarva/stats or a request that exceeds the cap.\n"
        "7. Do a real test-mode checkout from your pricing page for a full flow.\n"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
