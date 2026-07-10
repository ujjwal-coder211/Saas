"""GovernanceService facade + Team model (paper §16.1).

Ties RBAC, model allowlists, team budgets, skill pooling, and the audit view into
one governed surface. File-backed (teams.json + per-team ledgers) so it runs with
or without the SaaS Postgres DB.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from saas.governance.allowlist import enforce_plan
from saas.governance.audit_view import audit_summary
from saas.governance.budget import TeamBudget
from saas.governance.roles import ACTIONS, Role, can, require
from saas.governance.skill_pool import pool_skill, team_skills

_LOCK = threading.Lock()


@dataclass
class Team:
    id: str
    name: str
    tier: str = "business"  # team | business | enterprise
    members: dict[str, str] = field(default_factory=dict)  # user_id -> role
    model_allowlist: list[str] | None = None  # None = all models
    monthly_budget_usd: float = 100.0

    def role_of(self, user_id: str) -> Role | None:
        r = self.members.get(user_id)
        return Role(r) if r else None

    def to_dict(self) -> dict:
        return asdict(self)


class GovernanceService:
    def __init__(self, store_dir: str | Path):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._teams_path = self.store_dir / "teams.json"

    # ── persistence ──────────────────────────────────────────────────────────
    def _load(self) -> dict[str, dict]:
        if not self._teams_path.exists():
            return {}
        return json.loads(self._teams_path.read_text(encoding="utf-8"))

    def _save(self, teams: dict[str, dict]) -> None:
        self._teams_path.write_text(json.dumps(teams, indent=2), encoding="utf-8")

    def get_team(self, team_id: str) -> Team | None:
        raw = self._load().get(team_id)
        return Team(**raw) if raw else None

    # ── team + membership ────────────────────────────────────────────────────
    def create_team(self, team_id: str, name: str, owner_id: str, **kw) -> Team:
        with _LOCK:
            teams = self._load()
            if team_id in teams:
                raise ValueError(f"team exists: {team_id}")
            team = Team(id=team_id, name=name, members={owner_id: Role.OWNER.value}, **kw)
            teams[team_id] = team.to_dict()
            self._save(teams)
        return team

    def _require(self, team: Team, actor_id: str, action: str) -> None:
        role = team.role_of(actor_id)
        if role is None:
            raise PermissionError(f"user '{actor_id}' is not a member of team '{team.id}'")
        require(role, action)

    def set_member(self, team_id: str, actor_id: str, user_id: str, role: Role | str) -> Team:
        with _LOCK:
            teams = self._load()
            team = Team(**teams[team_id])
            self._require(team, actor_id, ACTIONS.MANAGE_MEMBERS)
            team.members[user_id] = Role(role).value
            teams[team_id] = team.to_dict()
            self._save(teams)
        return team

    def set_allowlist(self, team_id: str, actor_id: str, allowlist: list[str] | None) -> Team:
        with _LOCK:
            teams = self._load()
            team = Team(**teams[team_id])
            self._require(team, actor_id, ACTIONS.MANAGE_ALLOWLIST)
            team.model_allowlist = list(allowlist) if allowlist is not None else None
            teams[team_id] = team.to_dict()
            self._save(teams)
        return team

    def set_budget(self, team_id: str, actor_id: str, monthly_budget_usd: float) -> Team:
        with _LOCK:
            teams = self._load()
            team = Team(**teams[team_id])
            self._require(team, actor_id, ACTIONS.MANAGE_BUDGET)
            team.monthly_budget_usd = float(monthly_budget_usd)
            teams[team_id] = team.to_dict()
            self._save(teams)
        return team

    # ── enforcement helpers the request path calls ───────────────────────────
    def authorize(self, team_id: str, user_id: str, action: str) -> bool:
        team = self.get_team(team_id)
        if not team:
            return False
        role = team.role_of(user_id)
        return bool(role and can(role, action))

    def route_guard(self, team_id: str, primary: str, secondaries: list[str]) -> dict:
        team = self.get_team(team_id)
        allowlist = team.model_allowlist if team else None
        return enforce_plan(primary, secondaries, allowlist)

    def budget(self, team_id: str) -> TeamBudget:
        team = self.get_team(team_id)
        ceiling = team.monthly_budget_usd if team else 0.0
        return TeamBudget(team_id, ceiling, self.store_dir)

    def charge(self, team_id: str, cost_usd: float, *, actor: str = "team", model: str = "") -> dict:
        return self.budget(team_id).charge(cost_usd, actor=actor, model=model)

    # ── skill pooling ────────────────────────────────────────────────────────
    def pool_skill(self, team_id: str, actor_id: str, **skill) -> dict:
        team = self.get_team(team_id)
        if not team:
            return {"pooled": False, "reason": "no_such_team"}
        self._require(team, actor_id, ACTIONS.POOL_SKILLS)
        return pool_skill(self.store_dir, team_id, **skill)

    def team_skills(self, team_id: str) -> list[dict]:
        return team_skills(self.store_dir, team_id)

    # ── dashboard (RBAC-gated read surface) ──────────────────────────────────
    def dashboard(self, team_id: str, actor_id: str) -> dict:
        team = self.get_team(team_id)
        if not team:
            raise KeyError(team_id)
        self._require(team, actor_id, ACTIONS.VIEW_DASHBOARD)
        data = {
            "team": {
                "id": team.id,
                "name": team.name,
                "tier": team.tier,
                "members": team.members,
                "model_allowlist": team.model_allowlist,
            },
            "budget": self.budget(team_id).status(),
            "pooled_skills": self.team_skills(team_id),
        }
        # Audit view is admin/auditor-only.
        if self.authorize(team_id, actor_id, ACTIONS.VIEW_AUDIT):
            data["audit"] = audit_summary()
        return data
