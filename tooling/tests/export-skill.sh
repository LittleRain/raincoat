#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

cp -R "$ROOT_DIR/skills" "$TEST_TMP/skills"
cp -R "$ROOT_DIR/tooling" "$TEST_TMP/tooling"
cp "$ROOT_DIR/.gitignore" "$TEST_TMP/.gitignore"
mkdir -p "$TEST_TMP/exports"

# 全部用例都用这个合成技能，不引用任何真技能 —— 之前这份测试引用的
# personal-kb 已被删除（695b4ae），从那以后它一路是失败的。
FIXTURE="$TEST_TMP/skills/export-fixture"
mkdir -p "$FIXTURE/data" "$FIXTURE/lib" "$FIXTURE/keep" "$FIXTURE/junk/__pycache__"
printf -- '---\nname: export-fixture\ndescription: fixture\n---\n' >"$FIXTURE/SKILL.md"
printf '# Export Fixture\n' >"$FIXTURE/README.md"
printf '{"name": "export-fixture"}\n' >"$FIXTURE/skill.json"
printf 'x = 1\n' >"$FIXTURE/lib/lib.py"
printf 'notes\n' >"$FIXTURE/keep/notes.md"
printf '{"huge": true}\n' >"$FIXTURE/data/big.json"
printf '<html></html>\n' >"$FIXTURE/out.html"
printf 'junk\n' >"$FIXTURE/junk/__pycache__/x.pyc"
printf 'junk\n' >"$FIXTURE/.DS_Store"
# 技能自带的忽略规则：data/ 与 out.html 归它管，custom-should-survive/ 用来验证不被覆盖。
cat >"$FIXTURE/.gitignore" <<'EOF'
data/
out.html
__pycache__/
custom-should-survive/
EOF

pushd "$TEST_TMP" >/dev/null

# 1) 不在 git 工作区里：默认必须硬报错，而不是照抄整个目录。
if ./tooling/scripts/export-skill.sh export-fixture "$TEST_TMP/exports/no-git" \
  >"$TEST_TMP/no-git.out" 2>&1; then
  echo "expected export outside a git work tree to fail"
  exit 1
fi
grep -q -- '--loose' "$TEST_TMP/no-git.out"
test ! -e "$TEST_TMP/exports/no-git/SKILL.md"

# 2) --loose 逃生口：能导出，但仍排掉已知构建垃圾。
./tooling/scripts/export-skill.sh --loose export-fixture "$TEST_TMP/exports/loose" \
  >"$TEST_TMP/loose.out" 2>&1
test -f "$TEST_TMP/exports/loose/SKILL.md"
grep -q '警告' "$TEST_TMP/loose.out"
test ! -e "$TEST_TMP/exports/loose/junk/__pycache__/x.pyc"
# --loose 读不懂 .gitignore，所以这条本该被忽略的生成物会跟着走 —— 记录该模式的边界。
test -f "$TEST_TMP/exports/loose/data/big.json"

# 3) git 工作区里：只导出 git 会提交的那批文件。
git -C "$TEST_TMP" init -q

./tooling/scripts/export-skill.sh export-fixture "$TEST_TMP/exports/fixture" \
  >"$TEST_TMP/fixture.out"
test -f "$TEST_TMP/exports/fixture/SKILL.md"
test -f "$TEST_TMP/exports/fixture/README.md"
test -f "$TEST_TMP/exports/fixture/skill.json"
test -f "$TEST_TMP/exports/fixture/lib/lib.py"
test -f "$TEST_TMP/exports/fixture/keep/notes.md"
test ! -e "$TEST_TMP/exports/fixture/data/big.json"
test ! -e "$TEST_TMP/exports/fixture/out.html"
test ! -e "$TEST_TMP/exports/fixture/junk/__pycache__/x.pyc"
test ! -e "$TEST_TMP/exports/fixture/.DS_Store"
grep -q 'data/big.json' "$TEST_TMP/fixture.out"

# 4) 技能自带的 .gitignore 必须留下，且与样板条目合并（以前是被直接覆盖）。
test -f "$TEST_TMP/exports/fixture/.gitignore"
grep -q 'custom-should-survive' "$TEST_TMP/exports/fixture/.gitignore"
grep -q '^data/$' "$TEST_TMP/exports/fixture/.gitignore"
grep -q '^dist$' "$TEST_TMP/exports/fixture/.gitignore"

# 5) 目标目录非空 / 技能不存在，两条都要拦住。
mkdir -p "$TEST_TMP/exports/occupied"
printf 'x\n' >"$TEST_TMP/exports/occupied/file.txt"
if ./tooling/scripts/export-skill.sh export-fixture "$TEST_TMP/exports/occupied" \
  >"$TEST_TMP/occupied.out" 2>&1; then
  echo "expected non-empty destination to fail"
  exit 1
fi
if ./tooling/scripts/export-skill.sh missing-skill "$TEST_TMP/exports/missing" \
  >"$TEST_TMP/missing.out" 2>&1; then
  echo "expected missing skill export to fail"
  exit 1
fi

popd >/dev/null

echo "export-skill tests passed."
