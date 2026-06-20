"""Subscription plans and entitlements."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    monthly_tokens: int | None  # None = unlimited (PAYG)
    rate_limit_per_minute: int
    max_concurrent: int
    price_usd_monthly: float
    stripe_price_id: str | None = None


PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        monthly_tokens=50_000,
        rate_limit_per_minute=30,
        max_concurrent=3,
        price_usd_monthly=0.0,
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        monthly_tokens=2_000_000,
        rate_limit_per_minute=120,
        max_concurrent=10,
        price_usd_monthly=29.0,
        stripe_price_id=None,  # set STRIPE_PRICE_PRO in env
    ),
    "payg": Plan(
        id="payg",
        name="Pay as you go",
        monthly_tokens=None,
        rate_limit_per_minute=60,
        max_concurrent=5,
        price_usd_monthly=0.0,
    ),
}


def get_plan(plan_id: str) -> Plan:
    return PLANS.get(plan_id, PLANS["free"])


# Rough provider cost for margin monitoring (USD per 1M tokens blended)
COST_PER_MILLION_TOKENS_USD = 2.50
BILLING_MARKUP = 1.35


def estimate_cost_usd(tokens_total: int) -> float:
    if tokens_total <= 0:
        return 0.0
    base = (tokens_total / 1_000_000) * COST_PER_MILLION_TOKENS_USD
    return round(base * BILLING_MARKUP, 6)
