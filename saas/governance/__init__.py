"""Enterprise governance (paper §16.1).

Adds the org-facing controls the paper lists as differentiators — role-based
access, per-team budget ceilings with live dashboards, centralized audit views
over the §6.5 trail, model allowlists, and team skill pooling over Hermes —
as a pure-Python, file-backed domain layer that works with or without the SaaS
Postgres database.

Public surface:
    Role, can, ACTIONS                     — RBAC
    Team, GovernanceService                — team config + facade
    is_model_allowed, filter_models        — model allowlists
    TeamBudget                             — budget ceilings + live usage
    pool_skill, team_skills                — skill pooling
    audit_summary                          — centralized audit view
"""

from saas.governance.allowlist import filter_models, is_model_allowed  # noqa: F401
from saas.governance.audit_view import audit_summary  # noqa: F401
from saas.governance.budget import TeamBudget  # noqa: F401
from saas.governance.roles import ACTIONS, Role, can  # noqa: F401
from saas.governance.service import GovernanceService, Team  # noqa: F401
from saas.governance.skill_pool import pool_skill, team_skills  # noqa: F401
