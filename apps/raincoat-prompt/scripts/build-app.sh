#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 scripts/eval/validate_release.py
export CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-$PWD/.build/module-cache}"
mkdir -p "$CLANG_MODULE_CACHE_PATH"
flags=(--disable-sandbox --manifest-cache local --cache-path "$PWD/.build/cache"
    --config-path "$PWD/.build/config" --security-path "$PWD/.build/security")
swift build "${flags[@]}" --configuration release --product RaincoatPrompt
bin_path="$(swift build "${flags[@]}" --configuration release --show-bin-path)"

app="$PWD/dist/Raincoat Prompt.app"
rm -rf "$app/Contents/Resources"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
install -m 755 "$bin_path/RaincoatPrompt" "$app/Contents/MacOS/RaincoatPrompt"
install -m 644 assets/Info.plist "$app/Contents/Info.plist"
cp -R "$bin_path/RaincoatPrompt_PromptCore.bundle" "$app/Contents/Resources/"
codesign --force --sign - "$app"
printf '%s\n' "$app"
