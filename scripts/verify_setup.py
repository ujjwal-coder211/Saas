#!/usr/bin/env python3
"""
M0 — Foundation verification for Aksh by Aitotech.

Checks: Python imports, brain registry, docker-compose syntax, health smoke test.
Exit code 0 = all checks passed (warnings allowed); 1 = failures.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _warn(msg: str) -> None:
    print(f"  WARN  {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def check_imports() -> list[str]:
    errors: list[str] = []
    modules = [
        "neuralrouter.main",
        "neuralrouter.chat_service",
        "neuralrouter.omni_controller",
        "neuralrouter.work_modes",
        "neuralrouter.project_context",
        "neuralrouter.deploy.kit",
        "neuralrouter.security.scan",
        "neuralrouter.agent.agent_loop",
        "neuralrouter.search.web_search",
        "omni_training.brain_registry",
        "omni_training.scheduler",
        "omni_training.skill_ingest",
    ]
    for mod in modules:
        try:
            __import__(mod)
            _ok(f"import {mod}")
        except Exception as exc:
            _fail(f"import {mod}: {exc}")
            errors.append(mod)
    return errors


def check_brain_registry() -> list[str]:
    errors: list[str] = []
    reg_path = ROOT / "omni_training" / "brain_registry.json"
    if not reg_path.exists():
        _fail(f"missing {reg_path}")
        return ["brain_registry.json"]
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        active = data.get("active_version_id")
        versions = data.get("versions", {})
        if active not in versions:
            _fail(f"active_version_id '{active}' not in versions")
            errors.append("active_version_id")
        else:
            _ok(f"brain registry active={active} ({len(versions)} versions)")
    except Exception as exc:
        _fail(f"brain registry parse: {exc}")
        errors.append("brain_registry_parse")
    return errors


def check_docker_compose() -> list[str]:
    errors: list[str] = []
    compose = ROOT / "docker-compose.yml"
    if not compose.exists():
        _fail("docker-compose.yml missing")
        return ["docker-compose.yml"]
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose), "config"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        if result.returncode == 0:
            _ok("docker compose config (syntax valid)")
        else:
            _warn(f"docker compose unavailable or invalid: {result.stderr.strip()[:200]}")
    except FileNotFoundError:
        _warn("docker CLI not found — skipping compose syntax check")
    except subprocess.TimeoutExpired:
        _warn("docker compose config timed out")
    return errors


def check_health_smoke() -> list[str]:
    errors: list[str] = []
    try:
        from fastapi.testclient import TestClient
        from neuralrouter.main import app

        client = TestClient(app)
        r = client.get("/health")
        if r.status_code != 200:
            _fail(f"/health returned {r.status_code}")
            errors.append("health_status")
            return errors
        body = r.json()
        if body.get("status") != "ok":
            _fail(f"/health status={body.get('status')}")
            errors.append("health_body")
        else:
            _ok(f"/health smoke test (version={body.get('version')})")
        if "brain" not in body:
            _warn("/health missing extended brain field")
        if "search" not in body:
            _warn("/health missing extended search field")
    except Exception as exc:
        _fail(f"health smoke test: {exc}")
        errors.append("health_smoke")
    return errors


def main() -> int:
    print("Aksh M0 — verify_setup\n")
    all_errors: list[str] = []

    print("[1/4] Imports")
    all_errors.extend(check_imports())

    print("\n[2/4] Brain registry")
    all_errors.extend(check_brain_registry())

    print("\n[3/4] Docker Compose")
    all_errors.extend(check_docker_compose())

    print("\n[4/4] Health endpoint")
    all_errors.extend(check_health_smoke())

    print()
    if all_errors:
        print(f"FAILED — {len(all_errors)} check(s) need attention.")
        return 1
    print("PASSED — foundation ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
