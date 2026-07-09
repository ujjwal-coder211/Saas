"""Hermes skill curator — paper §5.2 (7-day cycle).

Skills are markdown files with YAML-ish frontmatter (paper §5.2.1):

    ---
    name: debug_async_race_condition
    task_type: code
    trigger: [async, race condition, deadlock]
    routing: deepseek
    success_rate: 0.87
    uses: 143
    last_used: 2026-07-09
    ---
    1. Read all async functions in scope
    2. ...

The curator runs on a cadence (default 7 days) and:
  - **Grade**   — read success_rate/uses.
  - **Prune**   — delete skills with success_rate < 0.5 after >= min_uses.
  - **Merge**   — combine skills with > overlap_threshold trigger overlap.
  - **Promote** — flag skills with success_rate > 0.9 and uses > 50 as priority.

Pure stdlib; a real scheduler (cron / the `schedule` skill) invokes `curate()`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SKILLS_DIR = Path(os.environ.get("SARVA_SKILLS_DIR", str(Path.home() / ".sarva" / "skills")))

PRUNE_BELOW = 0.5
MIN_USES_TO_PRUNE = 10
PROMOTE_ABOVE = 0.9
PROMOTE_MIN_USES = 50
OVERLAP_THRESHOLD = 0.8


@dataclass
class Skill:
    name: str
    path: Path
    task_type: str = "general"
    trigger: list[str] = field(default_factory=list)
    routing: str = ""
    success_rate: float = 0.0
    uses: int = 0
    last_used: str = ""
    priority: bool = False
    body: str = ""


def _parse(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    fm, body = (m.group(1), m.group(2)) if m else ("", text)
    meta: dict = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k] = v
    def f(key, d=0.0):
        try:
            return float(meta.get(key, d))
        except (TypeError, ValueError):
            return d
    return Skill(
        name=str(meta.get("name") or path.stem),
        path=path,
        task_type=str(meta.get("task_type") or "general"),
        trigger=meta.get("trigger") if isinstance(meta.get("trigger"), list) else [],
        routing=str(meta.get("routing") or ""),
        success_rate=f("success_rate"),
        uses=int(f("uses")),
        last_used=str(meta.get("last_used") or ""),
        priority=str(meta.get("priority", "")).lower() in ("1", "true", "yes"),
        body=body.strip(),
    )


def write_skill(skill: Skill) -> None:
    fm = (
        f"---\nname: {skill.name}\ntask_type: {skill.task_type}\n"
        f"trigger: [{', '.join(skill.trigger)}]\nrouting: {skill.routing}\n"
        f"success_rate: {skill.success_rate}\nuses: {skill.uses}\n"
        f"last_used: {skill.last_used}\npriority: {str(skill.priority).lower()}\n---\n"
    )
    skill.path.parent.mkdir(parents=True, exist_ok=True)
    skill.path.write_text(fm + skill.body + "\n", encoding="utf-8")


def load_skills(skills_dir: Path | None = None) -> list[Skill]:
    d = skills_dir or SKILLS_DIR
    if not d.exists():
        return []
    return [s for s in (_parse(p) for p in sorted(d.glob("*.md"))) if s]


def _overlap(a: list[str], b: list[str]) -> float:
    sa, sb = {x.lower() for x in a}, {x.lower() for x in b}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def curate(skills_dir: Path | None = None, *, dry_run: bool = False) -> dict:
    """Run one curation cycle. Returns a manifest of actions."""
    d = skills_dir or SKILLS_DIR
    skills = load_skills(d)
    pruned, promoted, merged = [], [], []

    # Prune weak, well-tried skills.
    survivors: list[Skill] = []
    for s in skills:
        if s.success_rate < PRUNE_BELOW and s.uses >= MIN_USES_TO_PRUNE:
            pruned.append(s.name)
            if not dry_run:
                try:
                    s.path.unlink()
                except OSError:
                    pass
        else:
            survivors.append(s)

    # Merge highly-overlapping survivors (keep the stronger one).
    kept: list[Skill] = []
    for s in survivors:
        dup = next((k for k in kept if _overlap(k.trigger, s.trigger) >= OVERLAP_THRESHOLD
                    and k.task_type == s.task_type), None)
        if dup:
            merged.append({"kept": dup.name, "merged_in": s.name})
            # combine triggers + uses, keep higher success rate
            dup.trigger = sorted(set(dup.trigger) | set(s.trigger))
            dup.uses += s.uses
            dup.success_rate = max(dup.success_rate, s.success_rate)
            if not dry_run:
                write_skill(dup)
                try:
                    s.path.unlink()
                except OSError:
                    pass
        else:
            kept.append(s)

    # Promote winners.
    for s in kept:
        should = s.success_rate > PROMOTE_ABOVE and s.uses > PROMOTE_MIN_USES
        if should and not s.priority:
            s.priority = True
            promoted.append(s.name)
            if not dry_run:
                write_skill(s)

    manifest = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "total_before": len(skills),
        "pruned": pruned,
        "merged": merged,
        "promoted": promoted,
        "total_after": len(kept),
        "dry_run": dry_run,
    }
    return manifest


if __name__ == "__main__":
    print(json.dumps(curate(), indent=2))
