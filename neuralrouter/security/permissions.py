"""Permission gate — security.check(plan) before Harness ACT (paper §3.2 / §6).

Every tool invocation crosses this gate. There is no privileged path from a
model decision to a real-world effect. MVP rules:

  - read-class tools: auto-approve
  - write / browser-mutate / system: require work-mode allow_write (or explicit confirm)
  - destructive shell patterns: always deny
  - deploy tools: require allow_deploy

Returns an Approval with reason for audit / RLEF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Tools that only observe — auto-approve.
READ_TOOLS = frozenset(
    {
        "read_file",
        "grep",
        "list_files",
        "security_scan",
        "git_status",
        "git_diff",
        "browser_extract",
        "browser_screenshot",
        "browser_wait",
        "screenshot_region",
    }
)

# Tools that mutate state / external world.
WRITE_TOOLS = frozenset(
    {
        "write_file",
        "generate_deploy_kit",
        "run_terminal",
        "git_commit",
        "browser_open",
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_execute",
        "open_app",
        "manage_clipboard",
        "notify",
    }
)

DEPLOY_TOOLS = frozenset({"generate_deploy_kit"})

# Shell patterns that must never auto-run (paper §6 excessive agency).
_DESTRUCTIVE_SHELL = re.compile(
    r"("
    r"\brm\s+-rf\b|\bdel\s+/[sS]\b|\bformat\s+"
    r"|\bmkfs\b|\bdd\s+if="
    r"|\bshutdown\b|\breboot\b"
    r"|\bcurl\b.*\|\s*(ba)?sh"
    r"|\bwget\b.*\|\s*(ba)?sh"
    r"|\bDrop-Database\b|\bRemove-Item\s+-Recurse\s+-Force\b"
    r")",
    re.IGNORECASE,
)


@dataclass
class Approval:
    approved: bool
    reason: str
    tool: str = ""
    risk: str = "low"  # low | medium | high | blocked
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "tool": self.tool,
            "risk": self.risk,
            "audit": self.audit,
        }


def check_plan(
    tool: str,
    args: dict[str, Any] | None = None,
    *,
    allow_write: bool = True,
    allow_deploy: bool = False,
    work_mode: str = "ship",
    from_untrusted: bool = False,
    context: str = "default",
) -> Approval:
    """Gate one Harness tool call. Call before run_tool().

    ``from_untrusted``: set when this action's proximate cause is untrusted
    (fetched/tool) content — the risk tier is escalated and, if that reaches
    ``blocked``, the action is denied (paper §6.3 structural escalation).
    ``context``: a stable key (e.g. project id / task type) for adaptive
    trust-promotion (§6.2).
    """
    approval = _evaluate(
        tool, args, allow_write=allow_write, allow_deploy=allow_deploy, work_mode=work_mode
    )
    return _finalize(approval, from_untrusted=from_untrusted, context=context)


def _finalize(approval: Approval, *, from_untrusted: bool, context: str = "default") -> Approval:
    from neuralrouter.security import adaptive as _adaptive
    from neuralrouter.security import audit as _audit
    from neuralrouter.security.injection import escalate_risk

    if from_untrusted and approval.approved:
        approval.risk = escalate_risk(approval.risk, from_untrusted=True)
        approval.audit = {**approval.audit, "from_untrusted": True}
        if approval.risk == "blocked":
            approval.approved = False
            approval.reason = "escalated_untrusted_content_blocked"

    # Adaptive trust (§6.2): record write-class decisions and expose promotion.
    if approval.tool and approval.risk in ("medium", "high"):
        _adaptive.record_approval(
            approval.tool, context=context, approved=approval.approved, risk=approval.risk
        )
    approval.audit = {
        **approval.audit,
        "promoted": _adaptive.is_promoted(approval.tool, context=context) if approval.tool else False,
    }

    _audit.record(
        "permission",
        tool=approval.tool,
        decision="approved" if approval.approved else "denied",
        risk=approval.risk,
        detail={**approval.audit, "reason": approval.reason},
    )
    return approval


def _evaluate(
    tool: str,
    args: dict[str, Any] | None = None,
    *,
    allow_write: bool = True,
    allow_deploy: bool = False,
    work_mode: str = "ship",
) -> Approval:
    args = args or {}
    audit = {"tool": tool, "work_mode": work_mode, "allow_write": allow_write}

    if tool not in READ_TOOLS and tool not in WRITE_TOOLS:
        return Approval(
            approved=False,
            reason=f"unknown_tool:{tool}",
            tool=tool,
            risk="blocked",
            audit=audit,
        )

    if tool in READ_TOOLS:
        return Approval(
            approved=True,
            reason="read_auto_approve",
            tool=tool,
            risk="low",
            audit=audit,
        )

    if tool in DEPLOY_TOOLS and not allow_deploy:
        return Approval(
            approved=False,
            reason="deploy_blocked_by_work_mode",
            tool=tool,
            risk="high",
            audit=audit,
        )

    if not allow_write:
        return Approval(
            approved=False,
            reason="write_blocked_read_only_mode",
            tool=tool,
            risk="medium",
            audit=audit,
        )

    if tool == "run_terminal":
        cmd = str(args.get("command") or args.get("cmd") or "")
        if _DESTRUCTIVE_SHELL.search(cmd):
            return Approval(
                approved=False,
                reason="destructive_shell_blocked",
                tool=tool,
                risk="blocked",
                audit={**audit, "command_preview": cmd[:200]},
            )
        return Approval(
            approved=True,
            reason="shell_allowed_non_destructive",
            tool=tool,
            risk="medium",
            audit={**audit, "command_preview": cmd[:200]},
        )

    risk = "high" if tool in ("browser_execute", "open_app", "git_commit") else "medium"
    return Approval(
        approved=True,
        reason="write_allowed_by_work_mode",
        tool=tool,
        risk=risk,
        audit=audit,
    )


# Alias matching paper loop name: await security.check(plan)
check = check_plan
