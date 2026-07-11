"""Per-team model allowlists (paper §16.1 governance / model allowlists).

An allowlist of ``None`` means "all registry models permitted". Otherwise only
listed model ids may be routed to for that team — enforced by filtering the
routing plan's models before dispatch, so a policy cannot route around it.
"""

from __future__ import annotations


def is_model_allowed(model_id: str, allowlist: list[str] | set[str] | None) -> bool:
    if allowlist is None:
        return True
    return model_id in set(allowlist)


def filter_models(models: list[str], allowlist: list[str] | set[str] | None) -> list[str]:
    """Drop any model not on the allowlist, preserving order."""
    if allowlist is None:
        return list(models)
    allowed = set(allowlist)
    return [m for m in models if m in allowed]


def enforce_plan(primary: str, secondaries: list[str], allowlist: list[str] | set[str] | None) -> dict:
    """Apply an allowlist to a routing plan.

    Returns the possibly-rewritten plan plus what was removed. If the primary is
    disallowed, the first allowed secondary is promoted; if none remain, the plan
    is flagged ``blocked`` so the caller escalates rather than silently dropping.
    """
    if allowlist is None:
        return {"primary": primary, "secondaries": list(secondaries), "removed": [], "blocked": False}

    allowed = set(allowlist)
    removed = [m for m in [primary, *secondaries] if m not in allowed]
    kept = [m for m in [primary, *secondaries] if m in allowed]
    if not kept:
        return {"primary": None, "secondaries": [], "removed": removed, "blocked": True}
    return {"primary": kept[0], "secondaries": kept[1:], "removed": removed, "blocked": False}
