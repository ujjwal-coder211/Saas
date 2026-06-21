#!/bin/bash
# Run on E2E Linux VM after git clone — builds and starts Aksh stack
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Copy .env.production.example to .env and edit secrets first."
  exit 1
fi

docker compose -f docker-compose.prod.yml up -d --build
echo ""
echo "Waiting for health..."
sleep 15
curl -sf "http://127.0.0.1:${AKSH_HTTP_PORT:-8000}/health" | head -c 500 || true
echo ""
echo "Done. Open http://YOUR_SERVER_IP:${AKSH_HTTP_PORT:-8000}/web/studio/"
