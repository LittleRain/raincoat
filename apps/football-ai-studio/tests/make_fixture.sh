#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/media
ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc2=size=1280x720:rate=24 -f lavfi -i sine=frequency=440 -t 4 -c:v libx264 -preset ultrafast -threads 2 -c:a aac data/media/synthetic-demo.mp4
echo "生成合成测试视频：$(pwd)/data/media/synthetic-demo.mp4（不是足球录像或 AI 识别结果）"
