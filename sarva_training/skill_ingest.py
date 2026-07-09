"""
Skill / MCP codebase → Sarva training rows.

When user clicks Add Skill/MCP in Aksh dashboard, register path or repo;
this module extracts SKILL.md, tool schemas, examples → vault-ready JSONL.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sarva_training.vault import RAW_LOG_PATH, vault_append

SKILLS_REGISTRY_PATH = Path(__file__).parent / "data" / "skills_registry.jsonl"


def _read_text(path: Path, max_chars: int = 50_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return ""


def _find_skill_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in ("SKILL.md", "skill.md", "README.md", "mcp.json", "tools.json"):
        found.extend(root.rglob(pattern))
    return found[:20]


def _extract_code_samples(root: Path, limit: int = 5) -> list[str]:
    samples: list[str] = []
    for ext in ("*.py", "*.ts", "*.js", "*.md"):
        for p in root.rglob(ext):
            if "node_modules" in p.parts or ".venv" in p.parts:
                continue
            text = _read_text(p, 4000)
            if len(text) > 100:
                samples.append(f"File: {p.name}\n{text}")
            if len(samples) >= limit:
                return samples
    return samples


def ingest_skill_path(
    *,
    tenant_id: str,
    skill_name: str,
    source_path: str,
    skill_type: str = "skill",
) -> dict:
    """
    Scan local or mounted skill/MCP directory → training examples + registry entry.
    """
    root = Path(source_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Skill path not found: {source_path}")

    skill_id = hashlib.sha256(f"{tenant_id}:{skill_name}:{source_path}".encode()).hexdigest()[:16]
    skill_docs = [_read_text(p) for p in _find_skill_files(root)]
    code_samples = _extract_code_samples(root)

    registry_row = {
        "skill_id": skill_id,
        "tenant_id": tenant_id,
        "name": skill_name,
        "type": skill_type,
        "source_path": str(root),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "files_scanned": len(skill_docs) + len(code_samples),
    }

    SKILLS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SKILLS_REGISTRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(registry_row, ensure_ascii=False) + "\n")

    training_rows_written = 0
    combined_doc = "\n\n---\n\n".join(d for d in skill_docs if d.strip())

    if combined_doc.strip():
        prompt = f"How do I use the Aksh skill/MCP '{skill_name}'? Explain tools and workflow."
        vault_append(
            RAW_LOG_PATH,
            {
                "row_id": f"skill_{skill_id}_doc",
                "tenant_id": tenant_id,
                "training_opt_in": True,
                "source": "skill_ingest",
                "skill_id": skill_id,
                "query": prompt,
                "model_response": combined_doc[:12000],
                "model_used": "skill_source",
                "expert_id": "skill-ingest",
                "research_notes": {
                    "teaching_focus": f"Learn skill {skill_name} API and usage",
                    "train_weight": 0.85,
                },
            },
        )
        training_rows_written += 1

    for i, sample in enumerate(code_samples):
        vault_append(
            RAW_LOG_PATH,
            {
                "row_id": f"skill_{skill_id}_code_{i}",
                "tenant_id": tenant_id,
                "training_opt_in": True,
                "source": "skill_ingest",
                "skill_id": skill_id,
                "query": f"Show example usage patterns from {skill_name} codebase.",
                "model_response": sample[:8000],
                "model_used": "skill_source",
                "expert_id": "skill-ingest",
            },
        )
        training_rows_written += 1

    return {
        "skill_id": skill_id,
        "name": skill_name,
        "training_rows_written": training_rows_written,
        "registry_path": str(SKILLS_REGISTRY_PATH),
    }


def ingest_from_git_url(tenant_id: str, skill_name: str, git_url: str) -> dict:
    """Clone via git then ingest — requires git on PATH."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="aksh_skill_") as tmp:
        subprocess.run(
            ["git", "clone", "--depth", "1", git_url, tmp],
            check=True,
            capture_output=True,
            text=True,
        )
        return ingest_skill_path(
            tenant_id=tenant_id,
            skill_name=skill_name,
            source_path=tmp,
            skill_type="mcp" if "mcp" in git_url.lower() else "skill",
        )
