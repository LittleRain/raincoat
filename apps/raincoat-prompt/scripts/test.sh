#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 scripts/eval/validate_cases.py
python3 scripts/eval/validate_release.py
python3 scripts/eval/structure_check.py
export CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-$PWD/.build/module-cache}"
mkdir -p "$CLANG_MODULE_CACHE_PATH"
developer_path="$(xcode-select -p)"
frameworks="$developer_path/Library/Developer/Frameworks"
testing_args=()
if [ -d "$frameworks/Testing.framework" ]; then
    testing_args=(-Xswiftc -F -Xswiftc "$frameworks" -Xlinker -rpath -Xlinker "$frameworks")
    if [ -f "$developer_path/Library/Developer/usr/lib/lib_TestingInterop.dylib" ]; then
        testing_args+=(-Xlinker -rpath -Xlinker "$developer_path/Library/Developer/usr/lib")
    fi
fi
swift test --disable-xctest --disable-sandbox --manifest-cache local \
    --cache-path "$PWD/.build/cache" --config-path "$PWD/.build/config" --security-path "$PWD/.build/security" \
    ${testing_args[@]+"${testing_args[@]}"}
