#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${1:-ubuntu@your-server}"
SERVER_APP_DIR="${2:-/srv/raincoat/app}"
SERVER_DEPLOY_DIR="${3:-/srv/raincoat}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REVISION="$(git -C "$ROOT_DIR" rev-parse HEAD)"
BUNDLE_PATH="/tmp/raincoat-$(date +%Y%m%d%H%M%S).bundle"

echo "[deploy] testing and building locally"
cd "$ROOT_DIR"
npm test
npm run build

echo "[deploy] creating git bundle for revision $REVISION"
git bundle create "$BUNDLE_PATH" "$REVISION"

echo "[deploy] uploading bundle to $SERVER_HOST"
scp "$BUNDLE_PATH" "$SERVER_HOST:/tmp/raincoat.bundle"

echo "[deploy] switching server checkout and restarting containers"
ssh "$SERVER_HOST" <<EOF
set -euo pipefail
mkdir -p "$SERVER_APP_DIR" "$SERVER_DEPLOY_DIR/data/uploads" "$SERVER_DEPLOY_DIR/data/runs" "$SERVER_DEPLOY_DIR/data/artifacts"
cd "$SERVER_APP_DIR"
if [ ! -d .git ]; then
  git init
fi
git fetch /tmp/raincoat.bundle "$REVISION"
git checkout -f "$REVISION"
docker compose -f infra/docker/docker-compose.yml up -d --build
curl -fsS http://localhost:3200/api/health
EOF

rm -f "$BUNDLE_PATH"
echo "[deploy] complete"
