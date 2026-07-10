"""Red-team + sensitive-path hardening tests (paper §6, §17)."""

from __future__ import annotations

import pytest

from neuralrouter.security.permissions import check_plan
from neuralrouter.security.redteam import ATTACKS, run_redteam


def test_all_attacks_defended():
    report = run_redteam()
    breaches = [r for r in report["results"] if not r["defended"]]
    assert report["all_defended"], f"breaches: {breaches}"
    assert report["total"] == len(ATTACKS)


def test_every_threat_category_covered():
    report = run_redteam()
    assert set(report["by_threat"]) == {
        "credential_theft",
        "prompt_injection",
        "excessive_agency",
        "session_hijack",
        "malicious_skills",
        "cost_runaway",
    }


@pytest.mark.parametrize(
    "path",
    [
        "~/.ssh/id_rsa",
        "~/.ssh/authorized_keys",
        "/home/u/.aws/credentials",
        "server.pem",
        "/etc/passwd",
        ".env",
        ".git-credentials",
    ],
)
def test_sensitive_paths_blocked(path):
    ap = check_plan("write_file", {"path": path}, allow_write=True)
    assert not ap.approved and ap.risk == "blocked"
    # reads too
    assert not check_plan("read_file", {"path": path}, allow_write=False).approved


@pytest.mark.parametrize("path", ["src/app.py", ".env.example", ".env.sample", "README.md"])
def test_benign_paths_allowed(path):
    assert check_plan("read_file", {"path": path}, allow_write=False).approved
    assert check_plan("write_file", {"path": path}, allow_write=True).approved


def test_loop_and_budget_guards():
    from neuralrouter.security.limits import BudgetGuard, LoopGuard

    g = LoopGuard(max_repeat=3)
    assert all(g.check("t", {"x": 1}) for _ in range(3))
    assert not g.check("t", {"x": 1})  # 4th identical trips
    assert g.tripped

    b = BudgetGuard(ceiling_usd=1.0)
    assert b.charge(0.5) and b.charge(0.5)
    assert not b.charge(0.5)  # over ceiling
    assert b.tripped


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
