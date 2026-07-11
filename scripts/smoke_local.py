"""Local readiness smoke-test — one command to confirm a working setup.

Boots the app in-process (no server/port needed) and checks the core endpoints:

    python scripts/smoke_local.py

/health, /v1/models, /v1/sarva/brain need no API key. If OPENROUTER_API_KEY is
set, it also runs a real /v1/chat round-trip through Sarva. Exit 0 = READY.
"""

from __future__ import annotations

import os
import sys

# Make the repo root importable when run as `python scripts/smoke_local.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("NEURALROUTER_ALLOW_UNAUTH", "true")


def main() -> int:
    from fastapi.testclient import TestClient

    from neuralrouter.main import app

    c = TestClient(app)
    ok = True

    r = c.get("/health")
    d = r.json() if r.status_code == 200 else {}
    brain = d.get("brain", {}).get("active_version_id")
    providers = d.get("providers", {})
    print(f"[/health]          {r.status_code}  brain={brain}  models={len(d.get('models_loaded', []))}")
    ok &= r.status_code == 200

    for path in ("/v1/models", "/v1/sarva/brain", "/api"):
        rr = c.get(path)
        print(f"[{path:<16}] {rr.status_code}")
        ok &= rr.status_code == 200

    if providers.get("openrouter"):
        rr = c.post("/v1/chat", json={"message": "reply with one word: hello"})
        ans = str(rr.json().get("answer", ""))[:60] if rr.status_code == 200 else rr.text[:120]
        print(f"[/v1/chat]         {rr.status_code}  -> {ans}")
        ok &= rr.status_code == 200
    else:
        print("[/v1/chat]         skipped — set OPENROUTER_API_KEY to test a live model call")

    print("\nRESULT:", "READY ✅" if ok else "NOT READY ❌")
    print("providers configured:", {k: v for k, v in providers.items()})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
