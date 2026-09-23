#!/usr/bin/env bash
# 真实 Chromium 跑「需人工」那一档的新界面：决策卡片 / 断链修复 / 撤销 / 都先留着。
#
# 为什么要单独一个浏览器测试：这几个交互全在页面里，靠 shell 断言只能验到脚本写没写盘，
# 验不到「卡片是不是被折回去了」「按钮改写的是不是另一个组」「请求里到点带没带 canonical_map」。
# 已经抓到过三个只有真浏览器才暴露的问题：单选框整表重渲染把卡片折回、卡片名没定位到就点到
# 列表里第一个同类按钮、#cfIgnored 加了按钮漏了 onClick。
#
# 依赖 playwright（仓库 package.json 已声明）+ 一个真实浏览器，缺任一个就跳过，不算失败。
set -uo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PYTHON=${PYTHON:-python3}
NODE=${NODE:-node}
# playwright 的浏览器缓存默认在真实家目录下；本脚本会把 HOME 换掉，所以路径得提前记下来
REAL_HOME="$HOME"

if ! NODE_PATH="$ROOT_DIR/node_modules" "$NODE" -e 'require("playwright")' >/dev/null 2>&1; then
  echo "[跳过] 没装 playwright（cd $ROOT_DIR && npm install），浏览器端交互未验证。"
  exit 0
fi
if [ ! -d "$REAL_HOME/Library/Caches/ms-playwright" ] && [ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
  echo "[跳过] 没找到 playwright 浏览器缓存（可先 npx playwright install chromium）。"
  exit 0
fi

T=$(mktemp -d "${TMPDIR:-/tmp}/skill-panel-ui.XXXXXX")
SRV=""
cleanup() {
  # 收尾整段静音：kill + wait 默认会让 shell 往 stderr 打一行 "Terminated"，
  # 那是收工噪音，不是测试结论。
  { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; } 2>/dev/null
  rm -rf "$T"
}
trap cleanup EXIT

mkdir -p "$T/home" "$T/fx/agenta/skills" "$T/fx/agentb/skills" "$T/fx/pool/skills"
cp -R "$ROOT_DIR/skills/skill-panel" "$T/sp"
rm -rf "$T/sp/data" "$T/sp/skill-panel.html"
find "$T/sp" -maxdepth 1 -name 'plan-*' -delete

mk() { # side name body [desc]
  mkdir -p "$T/fx/$1/skills/$2"
  printf -- '---\nname: %s\ndescription: %s\n---\n\n# %s\n\n%s\n' \
    "$2" "${3:-Use when exercising the manual conflict card in browser tests.}" "$2" "$4" \
    > "$T/fx/$1/skills/$2/SKILL.md"
}
# 逐字一致 → 可自动
mk agentb alpha-report "Use when exercising the manual conflict card in browser tests." "Same body."
cp -R "$T/fx/agentb/skills/alpha-report" "$T/fx/agenta/skills/alpha-report"
# 正文已分叉、两侧都可用 → 决策卡片（要人选）
mk agenta beta-report "Use when exercising the manual conflict card in browser tests." "Version A body."
mk agentb beta-report "Use when exercising the manual conflict card in browser tests." "Version B body, changed later."
# 断链 + 好副本 → 工具可自行修复
mk agentb link-broken "Use when exercising the manual conflict card in browser tests." "Real body."
cp -R "$T/fx/agentb/skills/link-broken" "$T/fx/agenta/tmp-real"
ln -s "$T/fx/agenta/tmp-real" "$T/fx/agenta/skills/link-broken"; rm -rf "$T/fx/agenta/tmp-real"
# 软链农场 → 必须交人工
printf -- '---\nname: link-farm\ndescription: Use when exercising the manual conflict card in browser tests.\n---\n\n# Link Farm\n\nBody written elsewhere.\n' > "$T/fx/agenta/elsewhere.md"
mkdir -p "$T/fx/agentb/skills/link-farm" "$T/fx/agenta/skills/link-farm"
mk agentb link-farm "Use when exercising the manual conflict card in browser tests." "Real body."
ln -s "$T/fx/agenta/elsewhere.md" "$T/fx/agenta/skills/link-farm/SKILL.md"

cat > "$T/sp/agents.json" <<JSON
{"agents":[{"id":"agenta","label":"A","supports_symlink":true,"install_hint":"$T/fx/agenta/skills","roots":[{"path":"$T/fx/agenta/skills","kind":"user_skills"}]},
           {"id":"agentb","label":"B","supports_symlink":true,"install_hint":"$T/fx/agentb/skills","roots":[{"path":"$T/fx/agentb/skills","kind":"user_skills"}]},
           {"id":"pool","label":"P","supports_symlink":true,"install_hint":"$T/fx/pool/skills","roots":[{"path":"$T/fx/pool/skills","kind":"shared_pool"}]}],"excluded":[]}
JSON

export HOME="$T/home"
cd "$T/sp/scripts" || exit 1
"$PYTHON" -u skillctl.py scan >/dev/null 2>&1 || { echo "scan 失败"; exit 1; }
"$PYTHON" -u skillctl.py serve --port 0 > "$T/serve.log" 2>&1 &
SRV=$!
for _ in $(seq 1 60); do grep -q 'token=' "$T/serve.log" && break; sleep 0.3; done
PORT=$(grep -o '127.0.0.1:[0-9]*' "$T/serve.log" | head -1 | cut -d: -f2)
TOKEN=$(grep -o 'token=[A-Za-z0-9_-]*' "$T/serve.log" | head -1 | cut -d= -f2)
[ -n "$PORT" ] && [ -n "$TOKEN" ] || { echo "服务没起来"; cat "$T/serve.log"; exit 1; }
FX="$T/fx"
echo "serve 在 $PORT"

PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$REAL_HOME/Library/Caches/ms-playwright}" \
NODE_PATH="$ROOT_DIR/node_modules" \
SHOT_DIR="$T" \
  "$NODE" "$ROOT_DIR/tooling/tests/skill-panel-ui.cjs" "http://127.0.0.1:${PORT}/?token=${TOKEN}"
RC=$?

echo "--- 磁盘终态 ---"
for side in agenta agentb; do
  for n in alpha-report beta-report link-broken link-farm; do
    p="$FX/$side/skills/$n"
    if [ -L "$p" ]; then echo "  $side/$n -> 软链 $(readlink "$p")"
    elif [ -d "$p" ]; then echo "  $side/$n 实体目录"
    else echo "  $side/$n 不存在"; fi
  done
done
echo "--- overrides.json ---"
"$PYTHON" -c "
import json
d = json.load(open('$T/sp/overrides.json'))
print('  by_conflict =', json.dumps(d.get('by_conflict'), ensure_ascii=False))
"
exit $RC
