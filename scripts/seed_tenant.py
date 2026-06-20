#!/usr/bin/env python3
"""Create a test SaaS tenant with API key."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neuralrouter.env_loader import load_dotenv  # noqa: F401

from saas.auth.api_keys import create_user_with_key
from saas.db.connection import saas_db_enabled


def main() -> int:
    if not saas_db_enabled():
        print("DATABASE_URL required")
        return 1
    email = sys.argv[1] if len(sys.argv) > 1 else "demo@aitotech.dev"
    result = create_user_with_key(email, "free")
    print(json.dumps(result, indent=2))
    print("\nSave api_key — shown once only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
