#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SKILLS_DIR="$ROOT_DIR/skills"

usage() {
  cat >&2 <<'EOF'
Usage: ./tooling/scripts/export-skill.sh [--loose] <skill-name> <destination-dir>

导出「git 会提交的那批文件」—— 被 .gitignore 覆盖的生成物
（data/、skill-panel.html、plan-*、__pycache__ 等）不会跟着走。

  --loose   不在 git 工作区里时使用：只按固定的构建垃圾名单排除，
            会丢掉 .gitignore 的语义，仅作逃生口。
EOF
}

LOOSE=0
if [[ "${1:-}" == "--loose" ]]; then
  LOOSE=1
  shift
fi

if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

SKILL_NAME="$1"
DEST_DIR="$2"
SOURCE_DIR="$SKILLS_DIR/$SKILL_NAME"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Skill not found: $SKILL_NAME" >&2
  exit 1
fi

if [[ -e "$DEST_DIR" ]] && [[ -n "$(find "$DEST_DIR" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
  echo "Destination directory must be empty: $DEST_DIR" >&2
  exit 1
fi

# 技能自带的 .gitignore 是导出仓库里唯一能挡住生成物的东西，
# 所以只补缺的条目，绝不覆盖已有的。
write_gitignore() {
  local target="$1/.gitignore"
  local boiler=".DS_Store
dist
coverage
.env
.env.*"
  if [[ -f "$target" ]]; then
    local line
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      grep -qxF "$line" "$target" || printf '%s\n' "$line" >>"$target"
    done <<<"$boiler"
  else
    printf '%s\n' "$boiler" >"$target"
  fi
}

in_git_worktree() {
  git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

copy_loose() {
  echo "警告：不在 git 工作区里，改用 --loose 的固定排除名单。" >&2
  echo "      这一模式无法读懂 .gitignore，可能导出本该被忽略的文件。" >&2
  tar -cf - -C "$SOURCE_DIR" \
    --exclude='.DS_Store' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='*.log' \
    . | tar -xf - -C "$DEST_DIR"
}

copy_via_git() {
  local list_file="$1" rel src dst count=0
  while IFS= read -r -d '' rel; do
    src="$ROOT_DIR/$rel"
    [[ -f "$src" || -L "$src" ]] || continue
    dst="$DEST_DIR/${rel#"skills/$SKILL_NAME/"}"
    mkdir -p "$(dirname "$dst")"
    cp -R "$src" "$dst"
    if [[ -L "$src" ]]; then
      echo "警告：导出内容里含软链 $rel（指向 $(readlink "$src")）" >&2
    fi
    count=$((count + 1))
  done <"$list_file"
  if [[ "$count" -eq 0 ]]; then
    echo "skills/$SKILL_NAME 下没有 git 认识的文件，拒绝导出一个空仓库。" >&2
    exit 1
  fi
  echo "已复制 $count 个文件"
}

mkdir -p "$DEST_DIR"

if in_git_worktree; then
  list_file=$(mktemp)
  trap 'rm -f "$list_file"' EXIT
  # --cached（已跟踪）+ --others --exclude-standard（未跟踪但没被忽略）
  # = git 会提交的那批文件，正好就是导出该带走的。
  git -C "$ROOT_DIR" ls-files -z --cached --others --exclude-standard \
    -- "skills/$SKILL_NAME" >"$list_file"
  copy_via_git "$list_file"

  ignored_file=$(mktemp)
  trap 'rm -f "$list_file" "$ignored_file"' EXIT
  git -C "$ROOT_DIR" ls-files -z --others --ignored --exclude-standard \
    -- "skills/$SKILL_NAME" >"$ignored_file"
  ignored=$(tr '\0' '\n' <"$ignored_file" | grep -c . || true)
  if [[ "$ignored" -gt 0 ]]; then
    echo "按 .gitignore 留下 $ignored 个生成物："
    tr '\0' '\n' <"$ignored_file" | grep . | head -5 | sed 's/^/  - /'
    [[ "$ignored" -gt 5 ]] && echo "  （还有 $((ignored - 5)) 个）"
  fi
else
  if [[ "$LOOSE" -eq 1 ]]; then
    copy_loose
  else
    echo "不在 git 工作区里，无法判断哪些文件该被忽略：$ROOT_DIR" >&2
    echo "请在 git 工作区里跑，或显式加 --loose 走固定排除名单。" >&2
    exit 1
  fi
fi

write_gitignore "$DEST_DIR"

echo "Exported $SKILL_NAME to $DEST_DIR"
