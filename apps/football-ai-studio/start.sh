#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo '请安装 Python 3.11+'; exit 1; }
command -v npm >/dev/null || { echo '请安装 Node.js 20.19+ 或 22.12+'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "需要 Python 3.11+"'
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --no-cache-dir -q -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
.venv/bin/python - <<'PY'
import os, shutil
from dotenv import load_dotenv
load_dotenv('.env')
for name, key in [('ffmpeg','FFMPEG_BIN'),('ffprobe','FFPROBE_BIN')]:
    if not shutil.which(os.getenv(key,name)):
        raise SystemExit(f'缺少 {name}，macOS 可执行 brew install ffmpeg')
PY
(cd frontend && npm ci --no-audit --no-fund --cache ../data/npm-cache && npm run build)
PORT=$(.venv/bin/python -c 'import os; from dotenv import load_dotenv; load_dotenv(".env"); print(int(os.getenv("FAS_PORT","8765")))')
echo "Football AI Studio P0: http://127.0.0.1:$PORT"
exec .venv/bin/python -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port "$PORT" --env-file .env --no-access-log
