#!/bin/bash
# 把 @local/dsh-peer-bridge 装进本机的 DSH profile（web + desktop）。
#
# 做三件事：
#   1) profile 的 package.json 增加 link 依赖，并把插件加进 dsh.profile.bundles
#   2) 在 profile 的 node_modules/@local/ 下建软链（等价于 pnpm 对 link 依赖的处理）
#   3) 打印接下来要做的重启步骤
#
# 幂等：重复执行不会重复添加。
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
PROFILES_DIR="$DSH_HOME/profiles"
NAME="@local/dsh-peer-bridge"
SLUG="dsh-peer-bridge"
# 合并前的两个包：装新包时一并摘掉，避免两个入口和 peer 文件双写
OLD_NAMES=("@local/dsh-open-in-peer" "@local/dsh-session-handoff" "@local/dsh-workspace-reconciler")
OLD_SLUGS=("dsh-open-in-peer" "dsh-session-handoff" "dsh-workspace-reconciler")

[ -d "$PROFILES_DIR" ] || { echo "找不到 $PROFILES_DIR"; exit 1; }

installed=0
for profile_dir in "$PROFILES_DIR"/*/; do
  profile="$(basename "$profile_dir")"
  pkg_file="$profile_dir/package.json"
  [ -f "$pkg_file" ] || continue

  if ! grep -q '"dsh"' "$pkg_file"; then
    echo "跳过 $profile（不是 DSH profile）"
    continue
  fi

  if [ "$profile" = "headless" ]; then
    echo "跳过 headless（无浏览器 UI，装上去只会变成一个假的交接目标）"
    continue
  fi

  cp -p "$pkg_file" "$pkg_file.bak-$(date +%Y%m%d-%H%M%S)"

  PROFILE_DIR="$profile_dir" PLUGIN_DIR="$PLUGIN_DIR" NAME="$NAME" OLD_NAMES="${OLD_NAMES[*]}" python3 - <<'PY'
import json, os, pathlib

profile_dir = pathlib.Path(os.environ['PROFILE_DIR'])
plugin_dir = os.environ['PLUGIN_DIR']
name = os.environ['NAME']
file = profile_dir / 'package.json'
data = json.loads(file.read_text())

deps = data.setdefault('dependencies', {})
for old in os.environ.get('OLD_NAMES', '').split():
    if old in deps:
        del deps[old]
        print(f'  已移除旧依赖 {old}')
if name not in deps:
    deps[name] = f'link:{plugin_dir}'

profile = data.setdefault('dsh', {}).setdefault('profile', {})
bundles = [b for b in profile.setdefault('bundles', []) if b not in set(os.environ.get('OLD_NAMES', '').split())]
profile['bundles'] = bundles
if name not in bundles:
    bundles.append(name)

file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print(f'  已写入 {file}')
PY

  mkdir -p "$profile_dir/node_modules/@local"
  target="$profile_dir/node_modules/@local/$SLUG"
  if [ -L "$target" ] || [ -e "$target" ]; then
    rm -rf "$target"
  fi
  ln -s "$PLUGIN_DIR" "$target"
  echo "  已链接 $target -> $PLUGIN_DIR"

  for old in "${OLD_SLUGS[@]}"; do
    old_target="$profile_dir/node_modules/@local/$old"
    if [ -L "$old_target" ] || [ -e "$old_target" ]; then
      rm -rf "$old_target"
      echo "  已移除旧软链 $old_target"
    fi
  done

  installed=$((installed + 1))
  echo "✔ profile $profile 已安装"
done

[ "$installed" -gt 0 ] || { echo "没有找到可安装的 profile"; exit 1; }

cat <<'TXT'

下一步（让两端都生效）：
  1) 重启 web host：  launchctl kickstart -k gui/$(id -u)/co.dsh.web
  2) 重启桌面端：     完全退出 DeepSeek Harness（Cmd+Q）后重新打开
  3) 确认登记：       ls ~/.dsh/handoff/peers/
      两个宿主各一个 <pid>.json，里面是各自的回环地址、profile 和带 token 的 URL。
  4) 确认共享令牌：   ls -l ~/.dsh/handoff/secret      # 0600，两个宿主读到同一份

注意：profile 的 pnpm-lock.yaml 未更新（手动建链，避免联网）。
      以后若在 profile 目录跑 pnpm install，请确认 link 依赖仍指向本仓库。
TXT
