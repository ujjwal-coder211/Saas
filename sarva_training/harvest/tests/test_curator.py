"""§5 Hermes curator tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sarva_training.skill_curator import Skill, curate, load_skills, write_skill


def _mk(d: Path, name, sr, uses, trigger, task_type="code", priority=False):
    write_skill(Skill(name=name, path=d / f"{name}.md", task_type=task_type,
                      trigger=trigger, success_rate=sr, uses=uses, priority=priority,
                      body="1. do the thing"))


def test_prune_weak(tmp_path):
    _mk(tmp_path, "weak", 0.3, 20, ["a", "b"])       # prune: low SR, enough uses
    _mk(tmp_path, "new_weak", 0.3, 3, ["c"])          # keep: too few uses
    _mk(tmp_path, "strong", 0.8, 30, ["d"])           # keep
    m = curate(tmp_path)
    assert "weak" in m["pruned"]
    assert "new_weak" not in m["pruned"]
    names = {s.name for s in load_skills(tmp_path)}
    assert "weak" not in names and "strong" in names and "new_weak" in names


def test_promote_winner(tmp_path):
    _mk(tmp_path, "champ", 0.95, 60, ["x"])
    m = curate(tmp_path)
    assert "champ" in m["promoted"]
    champ = [s for s in load_skills(tmp_path) if s.name == "champ"][0]
    assert champ.priority is True


def test_merge_overlap(tmp_path):
    _mk(tmp_path, "s1", 0.7, 20, ["async", "race", "deadlock", "lock"])
    _mk(tmp_path, "s2", 0.8, 15, ["async", "race", "deadlock", "lock"])  # 100% overlap
    m = curate(tmp_path)
    assert m["merged"], "expected a merge"
    remaining = load_skills(tmp_path)
    assert len(remaining) == 1
    # merged keeps combined triggers + summed uses
    assert remaining[0].uses == 35


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
