#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

PYTHON="${PYTHON:-python3}"
SKILL_DIR="$TEST_TMP/skill-panel"
FIXTURE="$TEST_TMP/fixture"
FAKE_HOME="$TEST_TMP/home"

cp -R "$ROOT_DIR/skills/skill-panel" "$SKILL_DIR"
# 拷出来的必须是「通用代码」那一份：产物不该住在 skill 目录里，
# 这里也顺手清掉开发机上跑出来的残留，好让后面的「目录保持干净」断言有意义。
find "$SKILL_DIR" -maxdepth 1 -name 'plan-*' -delete
rm -rf "$SKILL_DIR/data" "$SKILL_DIR/skill-panel.html"
mkdir -p "$FAKE_HOME" "$TEST_TMP/state"

# 写操作的台账（ledger.json）与回收站（trash/）都落在 $HOME/.skill-panel/ 下。
# 这里把 HOME 整个换掉，否则跑一次测试就会把 fakeagent 的记录写进跑测人真实的
# 台账里。必须在任何 skillctl.py 调用之前导出。
export HOME="$FAKE_HOME"

# ------------------------------------------------------------------ fixture
# 一棵完全合成的小树：同一份东西的两个副本 + 一条软链、一对已分叉的副本、
# 三类必现的 FAIL。这样测试不依赖本机上装了哪些 agent。

mkdir -p "$FIXTURE/agenta/skills/alpha-report" \
         "$FIXTURE/agenta/skills/beta-report" \
         "$FIXTURE/agenta/skills/no-skill-md" \
         "$FIXTURE/agenta/skills/leaky" \
         "$FIXTURE/agentb/skills/beta-report" \
         "$FIXTURE/agentb/skills/no-frontmatter" \
         "$FIXTURE/pool/skills" \
         "$FIXTURE/fakeagent/skills/switchable"

cat >"$FIXTURE/agenta/skills/alpha-report/SKILL.md" <<'SKILL'
---
name: alpha-report
description: >
  生成周度业务报告。当用户提到周报、周度数据、报告生成、指标拆解、
  环比同比时使用，需要输入表格数据并输出可读的 HTML 报告。
---

# Alpha Report

Step 1. Read the input table.
SKILL
mkdir -p "$FIXTURE/agenta/skills/alpha-report/scripts"
echo 'print("alpha")' >"$FIXTURE/agenta/skills/alpha-report/scripts/run.py"

# 逐字节一致的副本 —— 应判为真重复里的 identical
cp -R "$FIXTURE/agenta/skills/alpha-report" "$FIXTURE/agentb/skills/alpha-report"

# 共享池只放一条软链，实体仍在 agenta 下
ln -s "../../agenta/skills/alpha-report" "$FIXTURE/pool/skills/alpha-report"

# 正文已分叉的一对 —— 应判 divergent（需人工）
cat >"$FIXTURE/agenta/skills/beta-report/SKILL.md" <<'SKILL'
---
name: beta-report
description: Use when generating the beta business report from tabular input.
---

# Beta Report

Version A body.
SKILL
cat >"$FIXTURE/agentb/skills/beta-report/SKILL.md" <<'SKILL'
---
name: beta-report
description: Use when generating the beta business report from tabular input.
---

# Beta Report

Version B body, changed after the copy was made.
SKILL

# FAIL: 目录里有文件但没有 SKILL.md
mkdir -p "$FIXTURE/agenta/skills/no-skill-md"
echo "just notes" >"$FIXTURE/agenta/skills/no-skill-md/notes.md"

# FAIL: 有 SKILL.md 但没有 frontmatter
mkdir -p "$FIXTURE/agentb/skills/no-frontmatter"
cat >"$FIXTURE/agentb/skills/no-frontmatter/SKILL.md" <<'SKILL'
# No Frontmatter

This file starts straight with a heading.
SKILL

# FAIL: 脚本里写死凭据。token 在运行时拼出来，避免这段字面量本身落进仓库。
FAKE_TOKEN="sk-$(printf 'AAAA%.0s' 1 2 3 4 5)"
mkdir -p "$FIXTURE/agenta/skills/leaky/scripts"
printf 'api_key = "%s"\n' "$FAKE_TOKEN" >"$FIXTURE/agenta/skills/leaky/scripts/x.py"
cat >"$FIXTURE/agenta/skills/leaky/SKILL.md" <<'SKILL'
---
name: leaky
description: Use when testing that hardcoded credentials are detected and blocked.
---

# Leaky
SKILL

# 只被 fakeagent 持有 —— 用来验证开关写入与卸载，不污染上面的冲突分组
cat >"$FIXTURE/fakeagent/skills/switchable/SKILL.md" <<'SKILL'
---
name: switchable
description: Use when exercising the native toggle and uninstall paths in tests.
---

# Switchable
SKILL

# ------------------------------------------------------------------ 适配表

cat >"$SKILL_DIR/agents.json" <<JSON
{
  "_comment": "测试专用适配表：所有根目录都指向临时 fixture，不读本机真实 agent",
  "agents": [
    {
      "id": "agenta", "label": "Fixture A", "supports_symlink": true,
      "install_hint": "$FIXTURE/agenta/skills",
      "roots": [{"path": "$FIXTURE/agenta/skills", "kind": "user_skills", "label": "A 用户 skills"}]
    },
    {
      "id": "agentb", "label": "Fixture B", "supports_symlink": null,
      "install_hint": "$FIXTURE/agentb/skills",
      "roots": [{"path": "$FIXTURE/agentb/skills", "kind": "user_skills"}]
    },
    {
      "id": "pool", "label": "Fixture Pool", "supports_symlink": true,
      "install_hint": "$FIXTURE/pool/skills",
      "roots": [{"path": "$FIXTURE/pool/skills", "kind": "shared_pool"}]
    },
    {
      "id": "fakeagent", "label": "Fake Toggle", "supports_symlink": null,
      "install_hint": "$FIXTURE/fakeagent/skills",
      "roots": [{"path": "$FIXTURE/fakeagent/skills", "kind": "user_skills"}],
      "toggle": {
        "granularity": "skill", "writer": "json_nested",
        "file": "$TEST_TMP/state/fake-settings.json",
        "container": ["skillOverrides"], "value_mode": "scalar",
        "key_rule": "fm_name_or_dirname",
        "set": {"off": "off", "model_off": "user-invocable-only", "on": null},
        "state_labels": {"on": "启用", "model_off": "仅手动可用", "off": "已禁用"}
      }
    }
  ],
  "excluded": []
}
JSON

SCAN="$SKILL_DIR/scripts/skillctl.py"
# 产物落点：默认跟着 HOME 走，所以这里就是被隔离出来的那份 ~/.skill-panel/
ARTIFACTS="$FAKE_HOME/.skill-panel"
DATA="$ARTIFACTS/data/skills.json"
DASH="$ARTIFACTS/skill-panel.html"

# ------------------------------------------------------------------ 扫描

"$PYTHON" "$SCAN" scan >"$TEST_TMP/scan.out"

test -f "$DATA"
test -f "$DASH"

# 通用代码目录必须保持干净。产物写回 skill 目录，装到只读位置或会被整目录替换的
# 市场插件缓存里就会丢；这条断言就是钉住「代码与产物分家」。
for leaked in data skill-panel.html; do
  if [ -e "$SKILL_DIR/$leaked" ]; then
    echo "扫描产物写进了 skill 目录（$leaked），通用代码与本地产物没有分开"
    exit 1
  fi
done
if compgen -G "$SKILL_DIR/plan-*" > /dev/null; then
  echo "方案包写进了 skill 目录"
  exit 1
fi

# 页面必须是自包含且真的注入了数据，不是一个空模板
if grep -q '/\*__SKILL_DATA__\*/null' "$DASH"; then
  echo "dashboard was generated without injecting scan data"
  exit 1
fi
grep -q 'alpha-report' "$DASH"

"$PYTHON" - "$DATA" <<'PY'
import json
import sys
from collections import defaultdict

doc = json.load(open(sys.argv[1], encoding="utf-8"))

# 一个名字可能对应多条实体记录（每个 realpath 一条），必须先分组再断言
by_name = defaultdict(list)
for entity in doc["entities"]:
    by_name[entity["name"]].append(entity)
conflicts = {c["name"]: c for c in doc["conflicts"]}


def failures(entity):
    return [c["label"] for c in entity["checks"] if c["level"] == "fail"]


expected = {"alpha-report", "beta-report", "no-skill-md",
            "no-frontmatter", "leaky", "switchable"}
missing = expected - set(by_name)
assert not missing, f"扫描漏掉了这些 fixture: {sorted(missing)}"

# 同一份东西的 3 条记录 → 2 个实体，其中一条是共享池里的软链
alpha = by_name["alpha-report"]
assert len(alpha) == 2, [e["real_path"] for e in alpha]
holder = [e for e in alpha if e["link_agents"] == ["pool"]]
assert len(holder) == 1, [e["link_agents"] for e in alpha]
holder = holder[0]
assert holder["entity_agents"] == ["agenta"], holder["entity_agents"]
assert holder["link_count"] == 1, holder["link_count"]
# agentb 的那份是独立实体，不算在这个实体的引用里
assert sorted(holder["agents"]) == ["agenta", "pool"], holder["agents"]
other = [e for e in alpha if e is not holder][0]
assert other["entity_agents"] == ["agentb"], other["entity_agents"]
assert other["link_count"] == 0, other["link_count"]
for entity in alpha:
    assert not failures(entity), failures(entity)
    assert entity["type"] == "local", entity["type"]

# 正文一致 + 文件集一致 → 可自动处理
assert "alpha-report" in conflicts, "identical 副本没有进冲突清单"
group = conflicts["alpha-report"]
assert group["nature"] == "duplicate", group["nature"]
assert group["kind"] == "identical", group["kind"]
assert group["prescription"]["grade"] == "auto", group["prescription"]

# 正文已分叉 → 必须交人工，工具不得自作主张
beta = conflicts["beta-report"]
assert beta["kind"] == "divergent", beta["kind"]
assert beta["prescription"]["grade"] == "manual", beta["prescription"]
assert beta["prescription"]["needs_diff"] is True

# 三类必现 FAIL，且都要带证据
for name, needle in (("no-skill-md", "SKILL.md"),
                     ("no-frontmatter", "frontmatter"),
                     ("leaky", "凭据")):
    entity = by_name[name][0]
    hits = failures(entity)
    assert any(needle in label for label in hits), f"{name} 没报出预期 FAIL: {hits}"
    assert any(check["evidence"] for check in entity["checks"]
               if needle in check["label"]), f"{name} 的 FAIL 没有证据"

# 凭据规则要指到具体文件和行号
secret = [c for c in by_name["leaky"][0]["checks"] if c["level"] == "fail"][0]
assert any(ev["file"].endswith("x.py") for ev in secret["evidence"]), secret["evidence"]
assert all(ev["line"] > 0 for ev in secret["evidence"]), secret["evidence"]

# 只被一个 agent 持有的 skill 不该凭空产生冲突
assert "switchable" not in conflicts, "单副本被误判成冲突"

assert doc["stats"]["conflicts"] >= 2, doc["stats"]
print("fixture scan assertions passed")
PY

# ------------------------------------------------------------------ 单条查询

"$PYTHON" "$SCAN" check alpha-report >"$TEST_TMP/check.out"
grep -q 'alpha-report' "$TEST_TMP/check.out"

"$PYTHON" "$SCAN" agents >"$TEST_TMP/agents.out"
grep -q 'Fake Toggle' "$TEST_TMP/agents.out"
grep -q 'fake-settings.json' "$TEST_TMP/agents.out"

# ------------------------------------------------------------------ 安装指令

"$PYTHON" "$SCAN" install alpha-report --to agentb >"$TEST_TMP/install-unknown.out"
grep -q '复制优先' "$TEST_TMP/install-unknown.out"
grep -q 'symlink-target-unknown' "$TEST_TMP/install-unknown.out"

"$PYTHON" "$SCAN" install alpha-report --to agenta >"$TEST_TMP/install-known.out"
grep -q 'ln -s' "$TEST_TMP/install-known.out"
if grep -q '提示:' "$TEST_TMP/install-known.out"; then
  echo "软链支持已验证的 agent 不该出现未知提示"
  exit 1
fi

# ------------------------------------------------------------------ 方案包

"$PYTHON" "$SCAN" plan --grades auto,semi,manual >"$TEST_TMP/plan.out"
PLAN_MD=$(ls "$ARTIFACTS"/plan-*.md | head -1)
PLAN_SH=$(ls "$ARTIFACTS"/plan-*.sh | head -1)
test -f "$PLAN_MD"
test -f "$PLAN_SH"
grep -q 'alpha-report' "$PLAN_MD"
grep -q 'DRY_RUN' "$PLAN_SH"
if grep -qE '^[^#]*\b(rm -rf|rm -f)\b' "$PLAN_SH"; then
  echo "默认方案包不应该包含任何删除动作"
  exit 1
fi

# ------------------------------------------------------------------ 产物落点可换

ALT="$TEST_TMP/alt-root"
"$PYTHON" "$SCAN" scan --no-html --out "$ALT" >"$TEST_TMP/scan-out.out"
test -f "$ALT/data/skills.json"
grep -q "$ALT/data/skills.json" "$TEST_TMP/scan-out.out" || {
  echo "scan 没把落点打进输出，落点配错时人没法自查"
  exit 1
}

# --out 放子命令前面也得认（argparse 的子命令默认值会盖回父命名空间）
ALT2="$TEST_TMP/alt-root-2"
"$PYTHON" "$SCAN" --out "$ALT2" scan --no-html >/dev/null
test -f "$ALT2/data/skills.json"

# 环境变量同样生效
SKILL_PANEL_OUT="$TEST_TMP/env-root" "$PYTHON" "$SCAN" scan --no-html >/dev/null
test -f "$TEST_TMP/env-root/data/skills.json"

# 换了落点就得换一套状态：另一处没有快照时，报错必须说清找的是哪里
"$PYTHON" "$SCAN" check alpha-report --out "$TEST_TMP/empty-root" \
  >"$TEST_TMP/out-miss.out" 2>&1 && {
  echo "空落点居然读到了快照"
  exit 1
}
grep -q "$TEST_TMP/empty-root/data/skills.json" "$TEST_TMP/out-miss.out" || {
  echo "缺快照的报错没写明找的是哪个路径"
  exit 1
}

# ------------------------------------------------------------------ 原生开关

FAKE_SETTINGS="$TEST_TMP/state/fake-settings.json"

"$PYTHON" "$SCAN" disable switchable --agent fakeagent >"$TEST_TMP/disable-dry.out"
grep -q 'skillOverrides' "$TEST_TMP/disable-dry.out"
if [ -f "$FAKE_SETTINGS" ]; then
  echo "干跑不应该落盘"
  exit 1
fi

"$PYTHON" "$SCAN" disable switchable --agent fakeagent --yes >"$TEST_TMP/disable.out" 2>&1
"$PYTHON" - "$FAKE_SETTINGS" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc["skillOverrides"]["switchable"] == "off", doc
print("disable wrote the native toggle")
PY

# 台账必须落在隔离出来的 HOME 里。少了这条，HOME 隔离一旦回归就是静默污染
# 跑测人自己的 ~/.skill-panel/ledger.json，测试仍然全绿。
test -f "$FAKE_HOME/.skill-panel/ledger.json" || {
  echo "写操作没有落到隔离的 HOME 下，检查脚本是否导出了 HOME"
  exit 1
}

# 快照没见过刚落盘的改动 —— 必须主动说清，而不是让人以为工具没生效
"$PYTHON" "$SCAN" state switchable >"$TEST_TMP/state-stale.out" 2>&1
grep -q '上一次 scan' "$TEST_TMP/state-stale.out"
grep -q '重跑' "$TEST_TMP/state-stale.out"

"$PYTHON" "$SCAN" scan >"$TEST_TMP/rescan.out"
"$PYTHON" "$SCAN" state switchable >"$TEST_TMP/state-disabled.out"
grep -q '已禁用' "$TEST_TMP/state-disabled.out"

"$PYTHON" "$SCAN" enable switchable --agent fakeagent --yes >"$TEST_TMP/enable.out" 2>&1
"$PYTHON" - "$FAKE_SETTINGS" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert "switchable" not in doc.get("skillOverrides", {}), doc
print("enable restored the toggle")
PY

"$PYTHON" "$SCAN" scan >/dev/null
"$PYTHON" "$SCAN" state switchable >"$TEST_TMP/state-enabled.out"
grep -q '总状态：启用' "$TEST_TMP/state-enabled.out"

# ------------------------------------------------------------------ 卸载进回收站

"$PYTHON" "$SCAN" uninstall switchable --agent fakeagent --yes >"$TEST_TMP/uninstall.out"

test ! -d "$FIXTURE/fakeagent/skills/switchable"
TRASHED=$(find "$FAKE_HOME/.skill-panel/trash" -maxdepth 2 -name switchable | head -1)
test -n "$TRASHED"
test -f "$TRASHED/SKILL.md"

"$PYTHON" - "$FAKE_HOME/.skill-panel/ledger.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
actions = [a.get("action") for a in doc["actions"]]
assert actions, "写操作没有留痕"
assert all(actions), actions
print("ledger recorded:", actions)
PY

# ------------------------------------------------------------------ 配置写错必须硬报错

BROKEN="$TEST_TMP/broken"
cp -R "$SKILL_DIR" "$BROKEN"
"$PYTHON" - "$BROKEN/agents.json" <<'PY'
import json
import sys

path = sys.argv[1]
doc = json.load(open(path, encoding="utf-8"))
doc["agents"][3]["toggle"]["writer"] = "json_nestd"
json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("broke the writer value")
PY

set +e
"$PYTHON" "$BROKEN/scripts/skillctl.py" scan >"$TEST_TMP/broken.out" 2>&1
BROKEN_CODE=$?
set -e

test "$BROKEN_CODE" -eq 2
grep -q 'json_nestd' "$TEST_TMP/broken.out"

# ------------------------------------------------------------------ 旧产物要提示

# 老版本把产物写在 skill 目录里。读的是新落点，旧文件既不会报错也没人读，
# 所以必须主动说一句，否则人会以为「扫了却看不到」。
mkdir -p "$SKILL_DIR/data"
echo '{}' >"$SKILL_DIR/data/skills.json"
"$PYTHON" "$SCAN" scan --no-html >"$TEST_TMP/legacy.out"
grep -q '旧产物' "$TEST_TMP/legacy.out" || {
  echo "skill 目录里的旧产物没有被提示"
  exit 1
}
grep -q "$SKILL_DIR/data/skills.json" "$TEST_TMP/legacy.out" || {
  echo "旧产物提示没写清是哪个文件"
  exit 1
}
rm -rf "$SKILL_DIR/data"

# ------------------------------------------------------------------ 页面给出的命令要真能跑

# 页面上所有可复制命令都是 `cd <tool_dir> && <python> skillctl.py …`。
# 曾经 tool_dir 被写成 skill 根，用户照抄就是 can't open file '<skill>/skillctl.py'。
# 所以这里不做字符串断言，而是把页面里的 tool_dir/python_bin 解出来、原地跑一次。
"$PYTHON" - "$DASH" "$TEST_TMP" <<'PY'
import json
import os
import subprocess
import sys

dash, out_dir = sys.argv[1], sys.argv[2]
html = open(dash, encoding="utf-8").read()
head = "const DOC = "
i = html.index(head)
doc = json.loads(html[i + len(head):html.index("\n", i)].strip().rstrip(";"))

entry = os.path.join(doc["tool_dir"], "skillctl.py")
if not os.path.isfile(entry):
    raise SystemExit(f"页面里的 tool_dir 指不到入口脚本：{doc['tool_dir']}")

# 直接用页面上的拼法执行，连 cd 与 python 路径都照抄
cmd = f'cd "{doc["tool_dir"]}" && "{doc["python_bin"]}" skillctl.py plan --grades auto'
r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
if r.returncode != 0:
    raise SystemExit(f"页面给出的命令跑不通：{cmd}\n{r.stdout}{r.stderr}")

# 只读模式那几处展示用的命令同样要能跑
r = subprocess.run(["bash", "-lc",
                    f'cd "{doc["tool_dir"]}" && "{doc["python_bin"]}" skillctl.py agents'],
                   capture_output=True, text=True)
if r.returncode != 0:
    raise SystemExit(f"页面给出的 agents 命令跑不通\n{r.stdout}{r.stderr}")
open(os.path.join(out_dir, "emitted-command.out"), "w", encoding="utf-8").write(cmd + "\n")
PY

# ------------------------------------------------------------------ 单元测试

for suite in test_skillctl.py; do
  "$PYTHON" "$ROOT_DIR/skills/skill-panel/tests/$suite" >"$TEST_TMP/$suite.out" 2>&1 || {
    cat "$TEST_TMP/$suite.out"
    exit 1
  }
  grep -q '^OK' "$TEST_TMP/$suite.out"
done

echo "skill-panel tests passed."
