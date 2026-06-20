#!/usr/bin/env python3
"""Initialize PostgreSQL schema for SaaS (local dev without Docker)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neuralrouter.env_loader import load_dotenv  # noqa: F401

from saas.db.connection import run_schema_sql, saas_db_enabled


def main() -> int:
    if not saas_db_enabled():
        print("ERROR: Set DATABASE_URL in .env first")
        print("Example: postgresql+psycopg2://aitotech:aitotech_dev@localhost:5432/neuralrouter")
        return 1
    run_schema_sql()
    print("Schema applied OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
