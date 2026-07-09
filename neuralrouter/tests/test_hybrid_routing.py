"""Unit tests for hybrid routing, security gate, and context budget."""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on path when run as script or pytest from Saas/
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuralrouter.sarva_brain.context_budget import budget_context, estimate_tokens
from neuralrouter.sarva_brain.routing_policy import (
    CHEAP_SELF_MODEL,
    decide_routing,
    parse_trained_plan_json,
)
from neuralrouter.security.permissions import check_plan


def test_simple_query_can_self_handle():
    trace = decide_routing("what is a list in python", output_style="prose")
    assert trace.policy == "hybrid_rules_reasoning"
    assert trace.confidence > 0
    assert len(trace.reason_steps) >= 3
    if trace.self_executable:
        assert trace.routing_mode == "self_cheap"
        assert trace.primary_model == CHEAP_SELF_MODEL


def test_security_task_does_not_overclaim():
    trace = decide_routing(
        "audit this app for SQL injection vulnerability and design a secure architecture",
        output_style="code",
    )
    assert trace.task_type == "security"
    assert trace.self_executable is False
    assert "overclaim" in trace.reasoning_text().lower() or "delegate" in trace.reasoning_text().lower()


def test_high_complexity_forces_delegate():
    trace = decide_routing(
        "refactor the entire distributed system architecture and migrate the pipeline end to end step by step",
        output_style="code",
    )
    assert trace.complexity == "high"
    assert trace.self_executable is False


def test_hallucination_risk_prefers_grounding():
    trace = decide_routing(
        "what is the latest news and current price of nvidia stock today",
        output_style="prose",
    )
    assert trace.needs_grounding is True
    assert trace.self_executable is False


def test_reasoning_prefers_strong_teacher():
    trace = decide_routing(
        "why does this concurrency bug happen and how do I prove the root cause",
        output_style="prose",
    )
    assert trace.self_executable is False
    assert trace.primary_model in ("deepseek", "glm", "qwen", "llama", "mistral", "kimi")


def test_trained_json_respects_capability_bound():
    trace = parse_trained_plan_json(
        {
            "primary_model": "qwen",
            "confidence": 0.5,
            "self_executable": True,
            "task_type": "security",
            "complexity": "high",
            "reason": "I can do it",
        }
    )
    assert trace is not None
    assert trace.self_executable is False  # bound overrides overclaim


def test_security_read_auto_approve():
    a = check_plan("read_file", {"path": "a.py"}, allow_write=False)
    assert a.approved is True
    assert a.reason == "read_auto_approve"


def test_security_write_blocked_readonly():
    a = check_plan("write_file", {"path": "a.py"}, allow_write=False)
    assert a.approved is False
    assert "write_blocked" in a.reason


def test_security_destructive_shell_blocked():
    a = check_plan("run_terminal", {"command": "rm -rf /"}, allow_write=True)
    assert a.approved is False
    assert a.risk == "blocked"


def test_security_deploy_requires_flag():
    a = check_plan("generate_deploy_kit", {}, allow_write=True, allow_deploy=False)
    assert a.approved is False


def test_context_budget_truncates_history():
    history = [{"role": "user", "content": "x" * 500} for _ in range(50)]
    packet = budget_context(
        user_message="hello",
        history=history,
        codebase="code " * 10000,
        skills="skill " * 5000,
    )
    assert packet.token_estimate["total"] > 0
    assert estimate_tokens(packet.as_prompt_block()) <= packet.token_estimate["total"] + 50
    # Soft cap should keep total under ~140k tokens
    assert packet.token_estimate["total"] <= 150_000


def test_plan_turn_hybrid_wires_experts():
    from neuralrouter.sarva_controller import plan_turn

    plan = plan_turn("what is a variable")
    assert plan.routing_policy in ("hybrid_rules_reasoning", "trained_plus_bounds")
    assert plan.experts
    assert plan.reasoning
    assert "capability" in plan.capability_bound.lower() or "conductor" in plan.capability_bound.lower()
