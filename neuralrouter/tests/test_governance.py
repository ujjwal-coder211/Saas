"""Enterprise governance tests (paper §16.1)."""

from __future__ import annotations

import pytest

from saas.governance import ACTIONS, GovernanceService, Role, can
from saas.governance.allowlist import enforce_plan, filter_models
from saas.governance.roles import require


# ── RBAC ──────────────────────────────────────────────────────────────────────
def test_rbac_matrix():
    assert can(Role.OWNER, ACTIONS.DELETE_TEAM)
    assert can(Role.ADMIN, ACTIONS.MANAGE_BUDGET)
    assert not can(Role.DEVELOPER, ACTIONS.MANAGE_MEMBERS)
    assert not can(Role.VIEWER, ACTIONS.USE_AGENT)
    assert can(Role.VIEWER, ACTIONS.VIEW_DASHBOARD)
    with pytest.raises(PermissionError):
        require(Role.VIEWER, ACTIONS.MANAGE_ALLOWLIST)


# ── model allowlists ──────────────────────────────────────────────────────────
def test_allowlist_filtering_and_enforcement():
    assert filter_models(["qwen", "kimi", "glm"], ["qwen", "glm"]) == ["qwen", "glm"]
    assert filter_models(["qwen"], None) == ["qwen"]  # None = all allowed
    # primary disallowed → promote first allowed secondary
    plan = enforce_plan("kimi", ["qwen", "glm"], allowlist=["qwen", "glm"])
    assert plan["primary"] == "qwen" and "kimi" in plan["removed"]
    # nothing allowed → blocked, not silently dropped
    blocked = enforce_plan("kimi", ["nemotron"], allowlist=["qwen"])
    assert blocked["blocked"] is True and blocked["primary"] is None


# ── budgets ───────────────────────────────────────────────────────────────────
def test_team_budget_ceiling(tmp_path):
    svc = GovernanceService(tmp_path)
    svc.create_team("t1", "Acme", owner_id="u_owner", monthly_budget_usd=1.0)
    assert svc.charge("t1", 0.6, model="kimi")["allowed"]
    r = svc.charge("t1", 0.6, model="kimi")  # would exceed 1.0
    assert not r["allowed"] and r["tripped"]
    st = svc.budget("t1").status()
    assert st["spent_usd"] == pytest.approx(0.6)
    assert st["utilization"] == pytest.approx(0.6)


# ── membership + RBAC enforcement through the service ─────────────────────────
def test_service_membership_and_permission(tmp_path):
    svc = GovernanceService(tmp_path)
    svc.create_team("t2", "Beta", owner_id="owner")
    svc.set_member("t2", "owner", "dev1", Role.DEVELOPER)
    assert svc.authorize("t2", "dev1", ACTIONS.USE_AGENT)
    assert not svc.authorize("t2", "dev1", ACTIONS.MANAGE_BUDGET)
    # a developer cannot add members
    with pytest.raises(PermissionError):
        svc.set_member("t2", "dev1", "x", Role.VIEWER)
    # a non-member is rejected
    assert not svc.authorize("t2", "stranger", ACTIONS.VIEW_DASHBOARD)


# ── skill pooling ─────────────────────────────────────────────────────────────
def test_skill_pooling_respects_curator_floor(tmp_path):
    svc = GovernanceService(tmp_path)
    svc.create_team("t3", "Gamma", owner_id="owner")
    ok = svc.pool_skill("t3", "owner", skill_key="fast-auth", author="owner",
                        success_rate=0.9, trigger="add auth")
    assert ok["pooled"]
    weak = svc.pool_skill("t3", "owner", skill_key="flaky", author="owner",
                          success_rate=0.3, trigger="x")
    assert not weak["pooled"]
    keys = [s["skill_key"] for s in svc.team_skills("t3")]
    assert "fast-auth" in keys and "flaky" not in keys


# ── dashboard ─────────────────────────────────────────────────────────────────
def test_dashboard_gated_and_composed(tmp_path):
    svc = GovernanceService(tmp_path)
    svc.create_team("t4", "Delta", owner_id="owner", monthly_budget_usd=10.0,
                    model_allowlist=["qwen", "kimi"])
    svc.set_member("t4", "owner", "viewer1", Role.VIEWER)
    dash = svc.dashboard("t4", "owner")
    assert dash["team"]["model_allowlist"] == ["qwen", "kimi"]
    assert "budget" in dash and "audit" in dash  # owner sees audit
    # viewer sees dashboard but NOT the audit view
    vdash = svc.dashboard("t4", "viewer1")
    assert "audit" not in vdash
    # stranger blocked entirely
    with pytest.raises(PermissionError):
        svc.dashboard("t4", "stranger")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
