"""Role-based access control (paper §16.1 governance).

Four roles with a fixed permission matrix. `can(role, action)` is the single
gate the API/service consults before a governed action.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


# Governed actions.
class ACTIONS:
    USE_AGENT = "use_agent"
    POOL_SKILLS = "pool_skills"
    VIEW_USAGE = "view_usage"
    VIEW_AUDIT = "view_audit"
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_ALLOWLIST = "manage_allowlist"
    MANAGE_BUDGET = "manage_budget"
    DELETE_TEAM = "delete_team"


_ALL = {
    getattr(ACTIONS, a) for a in dir(ACTIONS) if not a.startswith("_")
}

_MATRIX: dict[Role, set[str]] = {
    Role.OWNER: set(_ALL),
    Role.ADMIN: {
        ACTIONS.USE_AGENT, ACTIONS.POOL_SKILLS, ACTIONS.VIEW_USAGE,
        ACTIONS.VIEW_AUDIT, ACTIONS.VIEW_DASHBOARD, ACTIONS.MANAGE_MEMBERS,
        ACTIONS.MANAGE_ALLOWLIST, ACTIONS.MANAGE_BUDGET,
    },
    Role.DEVELOPER: {
        ACTIONS.USE_AGENT, ACTIONS.POOL_SKILLS, ACTIONS.VIEW_USAGE,
        ACTIONS.VIEW_DASHBOARD,
    },
    Role.VIEWER: {ACTIONS.VIEW_USAGE, ACTIONS.VIEW_DASHBOARD},
}


def can(role: Role | str, action: str) -> bool:
    """True if the role may perform the action."""
    try:
        role = Role(role)
    except ValueError:
        return False
    return action in _MATRIX.get(role, set())


def require(role: Role | str, action: str) -> None:
    """Raise PermissionError if the role may not perform the action."""
    if not can(role, action):
        raise PermissionError(f"role '{role}' may not '{action}'")
