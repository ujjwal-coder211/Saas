#!/usr/bin/env sh
# Build apps/browser and copy dist into web/browser/ for FastAPI StaticFiles (/web/browser/).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/browser"
export VITE_ROUTELY_API_URL="${VITE_ROUTELY_API_URL:-https://api.routely.aitotech.in}"
npm ci
npm run build
rm -rf "$ROOT/web/browser"
mkdir -p "$ROOT/web/browser"
cp -r dist/* "$ROOT/web/browser/"
echo "Browser IDE copied to web/browser/ — serve at /web/browser/ after API deploy."
