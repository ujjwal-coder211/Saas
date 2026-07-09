"""Aksh Agent loop — plan → tool calls → synthesize (max 8 steps)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuralrouter.agent.tools import ALLOWED_TOOLS, run_tool
from neuralrouter.sarva_brain.guards import RunGuard
from neuralrouter.security.permissions import check_plan
from neuralrouter.work_modes import WorkScope, build_scope, scope_confirmation

MAX_STEPS = 8

_TOOL_CALL_RE = re.compile(
    r"```tool\s*\n(\{.*?\})\s*\n```",
    re.DOTALL,
)


@dataclass
class AgentStep:
    step: int
    kind: str
    content: str
    tool_result: dict[str, Any] | None = None


@dataclass
class AgentResult:
    answer: str
    steps: list[AgentStep] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    work_mode: str = "ship"
    scope_summary: str = ""


def _parse_tool_call(text: str) -> dict[str, Any] | None:
    m = _TOOL_CALL_RE.search(text)
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("tool")
    if name not in ALLOWED_TOOLS:
        return None
    return {"tool": name, "args": payload.get("args") or {}}


def _plan_prompt(task: str, file_context: str, rules: str, scope: WorkScope) -> str:
    ctx = file_context.strip() or "(no @file context)"
    rules_block = rules.strip() or "(no .akshrules)"
    tool_list = ", ".join(ALLOWED_TOOLS)
    return (
        "You are Aksh Agent (Sarva). Break the task into small steps.\n"
        f"{scope_confirmation(scope)}\n\n"
        "To call a tool, emit exactly one block:\n"
        "```tool\n"
        '{"tool": "read_file", "args": {"path": "src/main.py"}}\n'
        "```\n"
        f"Allowed tools: {tool_list}\n"
        f"Write allowed: {scope.allow_write}. Deploy tools allowed: {scope.allow_deploy}.\n\n"
        f"Project rules (.akshrules):\n{rules_block}\n\n"
        f"@file context:\n{ctx}\n\n"
        f"Task:\n{task}\n"
    )


def _synthesize_prompt(task: str, trace: list[AgentStep], scope: WorkScope) -> str:
    lines = [f"Task: {task}", f"Mode: {scope.label} — {scope.summary}", "", "Tool trace:"]
    for s in trace:
        lines.append(f"- Step {s.step} [{s.kind}]: {s.content[:500]}")
        if s.tool_result:
            lines.append(f"  Result: {json.dumps(s.tool_result, ensure_ascii=False)[:1200]}")
    lines.append("")
    lines.append(
        "Write the final answer for the user in simple English. "
        "Summarize what changed, what was scanned, or what to deploy next."
    )
    return "\n".join(lines)


async def run_agent_loop(
    task: str,
    *,
    file_context: str = "",
    rules: str = "",
    project_root: Path | None = None,
    work_mode: str = "auto",
    llm_plan: Any | None = None,
) -> AgentResult:
    if not llm_plan:
        raise ValueError(
            "Sarva Agent requires provider API keys (OpenRouter). "
            "Set OPENROUTER_API_KEY in .env and restart the server."
        )

    scope = build_scope(work_mode, task)  # type: ignore[arg-type]
    steps: list[AgentStep] = []
    tools_used: list[str] = []
    guard = RunGuard(max_steps=MAX_STEPS)  # §12: loop / budget / step runaway rail

    plan_input = _plan_prompt(task, file_context, rules, scope)
    plan_text = await llm_plan([{"role": "user", "content": plan_input}])
    steps.append(AgentStep(step=1, kind="plan", content=plan_text))

    observe_text = plan_text
    for i in range(2, MAX_STEPS + 1):
        call = _parse_tool_call(observe_text)
        if not call:
            break
        tool_name = call["tool"]
        # Paper §12 — loop / budget / step runaway guard before any action.
        gd = guard.before_action(tool_name, call["args"])
        if gd.aborted:
            steps.append(AgentStep(step=i, kind="guard_abort", content=gd.reason))
            break
        # Paper §3.2 / §6 — every Harness action crosses security.check(plan).
        approval = check_plan(
            tool_name,
            call["args"],
            allow_write=scope.allow_write,
            allow_deploy=scope.allow_deploy,
            work_mode=scope.mode,
        )
        if not approval.approved:
            result = {
                "ok": False,
                "error": f"security_gate_denied: {approval.reason}",
                "approval": approval.to_dict(),
            }
        else:
            result = run_tool(
                tool_name,
                call["args"],
                project_root=project_root,
                allow_write=scope.allow_write,
            )
            if isinstance(result, dict):
                result = {**result, "approval": approval.to_dict()}
        guard.after_action(tool_name, call["args"])
        tools_used.append(tool_name)
        steps.append(
            AgentStep(
                step=i,
                kind=f"tool:{tool_name}",
                content=json.dumps(call),
                tool_result=result,
            )
        )
        if i >= MAX_STEPS:
            break
        follow = await llm_plan(
            [
                {"role": "user", "content": plan_input},
                {"role": "assistant", "content": plan_text},
                {
                    "role": "user",
                    "content": f"Tool result:\n{json.dumps(result)}\nContinue with another tool or finish.",
                },
            ]
        )
        steps.append(AgentStep(step=i, kind="observe", content=follow))
        if "```tool" not in follow:
            break
        observe_text = follow

    synth_input = _synthesize_prompt(task, steps, scope)
    answer = await llm_plan([{"role": "user", "content": synth_input}])

    prefix = f"{scope_confirmation(scope)}\n\n"
    if not answer.startswith("["):
        answer = prefix + answer

    return AgentResult(
        answer=answer,
        steps=steps,
        tools_used=tools_used,
        work_mode=scope.mode,
        scope_summary=scope.summary,
    )
