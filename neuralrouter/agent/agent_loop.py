"""Aksh Agent loop — plan → tool calls → synthesize (max 5 steps)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuralrouter.agent.tools import ALLOWED_TOOLS, run_tool

MAX_STEPS = 5

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


def _plan_prompt(task: str, file_context: str, rules: str) -> str:
    ctx = file_context.strip() or "(no @file context)"
    rules_block = rules.strip() or "(no .akshrules)"
    return (
        "You are Aksh Agent. Break the task into small steps.\n"
        "To call a tool, emit exactly one block:\n"
        "```tool\n"
        '{"tool": "read_file", "args": {"path": "src/main.py"}}\n'
        "```\n"
        f"Allowed tools: {', '.join(ALLOWED_TOOLS)}\n\n"
        f"Project rules (.akshrules):\n{rules_block}\n\n"
        f"@file context:\n{ctx}\n\n"
        f"Task:\n{task}\n"
    )


def _synthesize_prompt(task: str, trace: list[AgentStep]) -> str:
    lines = [f"Task: {task}", "", "Tool trace:"]
    for s in trace:
        lines.append(f"- Step {s.step} [{s.kind}]: {s.content[:500]}")
        if s.tool_result:
            lines.append(f"  Result: {json.dumps(s.tool_result, ensure_ascii=False)[:800]}")
    lines.append("")
    lines.append("Write the final answer for the user. Be concise.")
    return "\n".join(lines)


async def run_agent_loop(
    task: str,
    *,
    file_context: str = "",
    rules: str = "",
    project_root: Path | None = None,
    llm_plan: Any | None = None,
) -> AgentResult:
    """
    MVP agent loop. Uses optional llm_plan(messages) -> str for planning/synthesis.
    Without LLM, returns a structured stub describing planned tool usage.
    """
    steps: list[AgentStep] = []
    tools_used: list[str] = []

    plan_input = _plan_prompt(task, file_context, rules)
    plan_text = plan_input
    if llm_plan:
        plan_text = await llm_plan([{"role": "user", "content": plan_input}])

    steps.append(AgentStep(step=1, kind="plan", content=plan_text))

    for i in range(2, MAX_STEPS + 1):
        call = _parse_tool_call(plan_text if i == 2 else steps[-1].content)
        if not call:
            break
        tool_name = call["tool"]
        result = run_tool(tool_name, call["args"], project_root=project_root)
        tools_used.append(tool_name)
        steps.append(
            AgentStep(
                step=i,
                kind=f"tool:{tool_name}",
                content=json.dumps(call),
                tool_result=result,
            )
        )
        if llm_plan and i < MAX_STEPS:
            follow = await llm_plan(
                [
                    {"role": "user", "content": plan_input},
                    {"role": "assistant", "content": plan_text},
                    {
                        "role": "user",
                        "content": f"Tool result:\n{json.dumps(result)}\nContinue or finish.",
                    },
                ]
            )
            steps.append(AgentStep(step=i, kind="observe", content=follow))
            if "```tool" not in follow:
                break
            plan_text = follow
        else:
            break

    synth_input = _synthesize_prompt(task, steps)
    if llm_plan:
        answer = await llm_plan([{"role": "user", "content": synth_input}])
    else:
        answer = (
            "Agent scaffold completed without LLM.\n"
            f"Steps: {len(steps)}. Tools: {', '.join(tools_used) or 'none'}.\n"
            "Connect provider keys to enable full autonomous agent."
        )

    return AgentResult(answer=answer, steps=steps, tools_used=tools_used)
