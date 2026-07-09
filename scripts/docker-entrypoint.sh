#!/bin/sh
set -e

echo "[Aksh] Waiting for PostgreSQL..."
python <<'PY'
import os
import sys
import time

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("DATABASE_URL not set — skipping wait")
    sys.exit(0)

try:
    import psycopg2
except ImportError:
    sys.exit(0)

conn_url = url.replace("postgresql+psycopg2://", "postgresql://")
for i in range(90):
    try:
        conn = psycopg2.connect(conn_url)
        conn.close()
        print("[Aksh] Database is ready")
        sys.exit(0)
    except Exception:
        time.sleep(1)
print("[Aksh] Database wait timed out", file=sys.stderr)
sys.exit(1)
PY

echo "[Aksh] Applying schema (idempotent)..."
python scripts/init_db.py || true

mkdir -p /app/data/projects /app/sarva_training/data/vault

echo "[Aksh] Starting API on port ${PORT:-8000}..."
exec uvicorn neuralrouter.main:app --host 0.0.0.0 --port "${PORT:-8000}"
