"""Centralized audit view (paper §16.1: centralized audit views over the §6.5 trail).

Aggregates the append-only security audit log (neuralrouter.security.audit) into a
compliance dashboard: decision/risk breakdowns, denied high-risk actions, and the
most recent events — the read surface an admin/auditor consumes.
"""

from __future__ import annotations

from collections import Counter


def audit_summary(limit: int = 500) -> dict:
    """Roll up the last ``limit`` audit events for a governance dashboard."""
    from neuralrouter.security.audit import tail

    events = tail(limit)
    decisions = Counter(e.get("decision") for e in events if e.get("decision"))
    risks = Counter(e.get("risk") for e in events if e.get("risk"))
    event_types = Counter(e.get("event") for e in events if e.get("event"))
    tools = Counter(e.get("tool") for e in events if e.get("tool"))

    denied_high = [
        e
        for e in events
        if e.get("decision") == "denied" and e.get("risk") in ("high", "blocked")
    ]
    return {
        "events_examined": len(events),
        "by_decision": dict(decisions),
        "by_risk": dict(risks),
        "by_event": dict(event_types),
        "top_tools": dict(tools.most_common(10)),
        "denied_high_risk_count": len(denied_high),
        "denied_high_risk_recent": denied_high[-10:],
        "compliance_note": (
            "Append-only trail; substrate for SOC 2 / GDPR / HIPAA / ISO 27001 "
            "evidence (paper §16.1)."
        ),
    }
