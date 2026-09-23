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

# 正文一致但文件集不同的一对 —— 应判 same-body-diff-files（半自动）。
# 专供批量去重那条路：一组的 SKILL.md 逐字一致，只有 agenta 那边多长了一个脚本，
# 也就是「复制过去之后各自又长了东西」的典型形态。
mkdir -p "$FIXTURE/agenta/skills/gamma-report/scripts" "$FIXTURE/agentb/skills/gamma-report"
cat >"$FIXTURE/agenta/skills/gamma-report/SKILL.md" <<'SKILL'
---
name: gamma-report
description: Use when checking that a copy which grew extra files counts as semi-automatic.
---

# Gamma Report

Shared body; one side carries an extra script.
SKILL
echo 'print("gamma")' >"$FIXTURE/agenta/skills/gamma-report/scripts/extra.py"
cp "$FIXTURE/agenta/skills/gamma-report/SKILL.md" \
   "$FIXTURE/agentb/skills/gamma-report/SKILL.md"

# 断链：一份指向空气的快捷方式 + 一份好副本。这一档没有取舍 —— 把链指回正本不涉及任何
# 内容取舍（后面本来什么都没有），工具该自己修好。实测本机 ~/.claude/skills/find-skills
# 就是这种形态，而它以前还会被选成正本。
mkdir -p "$FIXTURE/agentb/skills/link-broken"
cat >"$FIXTURE/agentb/skills/link-broken/SKILL.md" <<'SKILL'
---
name: link-broken
description: Use when checking that a dangling copy gets repointed at the good one.
---

# Link Broken

The real copy lives on the other side.
SKILL
ln -s "$FIXTURE/agenta/gone/link-broken" "$FIXTURE/agenta/skills/link-broken"

# 软链农场：目录里只有一条软链、没有自己的文件。这一档**不能**自动处理 —— 那些链可能各自
# 指向不同地方，换掉就是丢映射。要让正文真的不同才落进 divergent 那一档，所以这条链指向
# 的是另一个文件（内容与 agentb 那份不一样）。
cat >"$FIXTURE/agenta/elsewhere-link-farm.md" <<'SKILL'
---
name: link-farm
description: Use when checking that a link-only copy is left for a human to decide.
---

# Link Farm

Body written somewhere else entirely.
SKILL
mkdir -p "$FIXTURE/agentb/skills/link-farm"
cat >"$FIXTURE/agentb/skills/link-farm/SKILL.md" <<'SKILL'
---
name: link-farm
description: Use when checking that a link-only copy is left for a human to decide.
---

# Link Farm

The real copy lives on the other side.
SKILL
mkdir -p "$FIXTURE/agenta/skills/link-farm"
ln -s "$FIXTURE/agenta/elsewhere-link-farm.md" \
   "$FIXTURE/agenta/skills/link-farm/SKILL.md"

# 真分叉 + 一条断链：两侧正文都真有改动，不能因为「还有条断链」就把整组当可自动。
mkdir -p "$FIXTURE/agenta/skills/mixed-report" "$FIXTURE/agentb/skills/mixed-report"
cat >"$FIXTURE/agenta/skills/mixed-report/SKILL.md" <<'SKILL'
---
name: mixed-report
description: Use when checking that real divergence is never auto resolved in tests.
---

# Mixed Report

Version A body, changed on this side.
SKILL
cat >"$FIXTURE/agentb/skills/mixed-report/SKILL.md" <<'SKILL'
---
name: mixed-report
description: Use when checking that real divergence is never auto resolved in tests.
---

# Mixed Report

Version B body, changed on that side instead.
SKILL
ln -s "$FIXTURE/agenta/gone/mixed-report" "$FIXTURE/pool/skills/mixed-report"

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
    echo "扫描产物写进了 skill 目录（${leaked}），通用代码与本地产物没有分开"
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

# 批量去重必须带「含半自动」开关，并且真的把开关状态传给后端。这条防的是老毛病
# 复发：半自动档曾经只让单组点，前端把批量过滤硬编码成 grade==auto，后端明明支持。
grep -q 'id="bulkSemi"' "$DASH" || { echo "批量栏没有「含半自动」开关"; exit 1; }
grep -q 'state.withSemi' "$DASH" || { echo "批量去重没读「含半自动」开关"; exit 1; }
grep -q 'allow_semi' "$DASH" || { echo "页面没把 allow_semi 传给后端"; exit 1; }

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


expected = {"alpha-report", "beta-report", "gamma-report", "no-skill-md",
            "no-frontmatter", "leaky", "switchable", "link-broken", "link-farm",
            "mixed-report"}
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

# 正文已分叉 → 必须交人工：工具不替你挑，但要给得起「选哪一份」的候选与推荐。
# （以前这档只给一条 diff 命令；现在页面上给的是选正本的卡片，所以不再需要 needs_diff。）
beta = conflicts["beta-report"]
assert beta["kind"] == "divergent", beta["kind"]
assert beta["prescription"]["grade"] == "manual", beta["prescription"]
assert not beta["prescription"]["needs_diff"], beta["prescription"]
assert beta["prescription"]["shape"], beta["prescription"]
assert len(beta["prescription"]["candidates"]) == beta["count"], beta["prescription"]["candidates"]
assert beta["prescription"]["canonical"], beta["prescription"]
assert all(c["mtime"] > 0 for c in beta["prescription"]["candidates"]), \
    beta["prescription"]["candidates"]

# 正文一致但文件集不同 → 半自动。它必须给出正本与改写清单，
# 否则页面上的批量去重就算勾了「含半自动」也无从下手。
gamma = conflicts["gamma-report"]
assert gamma["kind"] == "same-body-diff-files", gamma["kind"]
assert gamma["prescription"]["grade"] == "semi", gamma["prescription"]
assert gamma["prescription"]["canonical"], gamma["prescription"]
assert gamma["prescription"]["rewrite"], gamma["prescription"]
# 半自动档的正文是逐字一致的，不能给它贴「正文各有改动」的标签（那是分叉档的说法）。
assert not gamma["prescription"].get("shape"), gamma["prescription"].get("shape")
assert gamma["prescription"]["canonical_why"].startswith("文件最全"), \
    gamma["prescription"]["canonical_why"]

# 断链那份：不能当正本，正本得落在真副本上，而且链在哪儿要记下来（不然没处修）。
broken = conflicts["link-broken"]
assert broken["prescription"]["shape"] == "broken", broken["prescription"]
bad = [e for e in broken["entities"] if not e["path_exists"]]
assert len(bad) == 1, [e["path_exists"] for e in broken["entities"]]
assert bad[0]["link_at"], bad[0]
assert broken["prescription"]["canonical"] != bad[0]["real_path"], broken["prescription"]
cands = {c["path"]: c for c in broken["prescription"]["candidates"]}
assert cands[bad[0]["real_path"]]["usable"] is False, cands[bad[0]["real_path"]]
assert "不存在" in cands[bad[0]["real_path"]]["why"], cands[bad[0]["real_path"]]

# 软链农场那份：同样不能当正本（目录里全是软链、没有自己的文件）。
farm = conflicts["link-farm"]
assert farm["prescription"]["shape"] == "symlink-farm", farm["prescription"]
link_only = [e for e in farm["entities"]
             if not e["real_file_count"] and e["link_file_count"]]
assert len(link_only) == 1, [e["real_file_count"] for e in farm["entities"]]
farm_cands = {c["path"]: c for c in farm["prescription"]["candidates"]}
assert farm_cands[link_only[0]["real_path"]]["usable"] is False, \
    farm_cands[link_only[0]["real_path"]]
assert "没有自己的文件" in farm_cands[link_only[0]["real_path"]]["why"], \
    farm_cands[link_only[0]["real_path"]]

# 真分叉 + 断链：正本、候选、形态都要对，重点是它必须仍然算「交人工」。
mixed = conflicts["mixed-report"]
assert mixed["prescription"]["grade"] == "manual", mixed["prescription"]
assert mixed["prescription"]["shape"] == "broken", mixed["prescription"]

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

# ------------------------------------------------------------------ 一键去重要真能落盘

# 这是唯一会把「一个真实目录换成软链」的路径，三条硬约束都得在真环境里验：
# 干跑一个字节不动、落盘后原副本进回收站、再点一次不会把正本自己干掉。
DUP_COPY="$FIXTURE/agentb/skills/alpha-report"
CANON="$FIXTURE/agenta/skills/alpha-report"
LEDGER="$FAKE_HOME/.skill-panel/ledger.json"

if [ ! -d "$DUP_COPY" ] || [ -L "$DUP_COPY" ]; then
  echo "fixture 前提不成立：$DUP_COPY 应当是实体目录"
  exit 1
fi

LEDGER_BEFORE=$(cat "$LEDGER" 2>/dev/null || echo "")
"$PYTHON" "$SCAN" resolve --names alpha-report >"$TEST_TMP/resolve-dry.out"

grep -q '干跑预览' "$TEST_TMP/resolve-dry.out" || {
  echo "resolve 缺省不是干跑"
  exit 1
}
if [ -L "$DUP_COPY" ]; then
  echo "干跑就把目录换成了快捷方式"
  exit 1
fi
[ -d "$DUP_COPY" ] || { echo "干跑动了副本目录"; exit 1; }
[ "$LEDGER_BEFORE" = "$(cat "$LEDGER" 2>/dev/null || echo "")" ] || {
  echo "干跑写了台账"
  exit 1
}

"$PYTHON" "$SCAN" resolve --names alpha-report --yes >"$TEST_TMP/resolve.out"

[ -L "$DUP_COPY" ] || { echo "落盘后副本没变成快捷方式"; exit 1; }
[ -f "$DUP_COPY/SKILL.md" ] || { echo "快捷方式读不到内容"; exit 1; }
[ -d "$CANON" ] && [ ! -L "$CANON" ] || { echo "正本被动过了"; exit 1; }

TRASHED=$(find "$FAKE_HOME/.skill-panel/trash" -name alpha-report -type d 2>/dev/null | head -1)
[ -n "$TRASHED" ] || { echo "被换掉的副本没进回收站"; exit 1; }
[ -f "$TRASHED/SKILL.md" ] || { echo "回收站里的副本内容不全"; exit 1; }

grep -q 'resolve-conflict' "$LEDGER" || { echo "台账没记这次去重"; exit 1; }

# 连点第二下必须是空操作 —— 否则第二次会把正本自己换掉
"$PYTHON" "$SCAN" resolve --names alpha-report --yes >"$TEST_TMP/resolve-again.out"
[ -d "$CANON" ] && [ ! -L "$CANON" ] || { echo "重复执行把正本弄没了"; exit 1; }

# ------------------------------------------------------------------ 批量去重（含半自动）

# 页面上的批量「一键去重」走的就是这里 —— 同名多组一起传，半自动由 allow_semi
# 决定带不带。三条硬约束照旧：不带 --semi 时半自动组一个字节都不许动、带了也先
# 干跑、落盘后原副本（连同它独有的文件）必须整份躺在回收站里。

SEMI_DUP="$FIXTURE/agentb/skills/gamma-report"
if [ -L "$SEMI_DUP" ]; then
  echo "fixture 前提不成立：$SEMI_DUP 应当是实体目录"
  exit 1
fi

"$PYTHON" "$SCAN" resolve --names alpha-report,gamma-report \
  >"$TEST_TMP/resolve-batch-nosemi.out" 2>&1
if [ -L "$SEMI_DUP" ]; then
  echo "没加 --semi 的批量去重动了半自动组"
  exit 1
fi
grep -q '半自动' "$TEST_TMP/resolve-batch-nosemi.out" || {
  echo "批量去重跳过半自动组时没说明原因"
  exit 1
}

"$PYTHON" "$SCAN" resolve --names alpha-report,gamma-report --semi \
  >"$TEST_TMP/resolve-batch-dry.out"
grep -q '干跑预览' "$TEST_TMP/resolve-batch-dry.out" || {
  echo "批量 + --semi 缺省不是干跑"
  exit 1
}
[ -d "$SEMI_DUP" ] && [ ! -L "$SEMI_DUP" ] || { echo "批量干跑就换了半自动组的副本"; exit 1; }

"$PYTHON" "$SCAN" resolve --names alpha-report,gamma-report --semi --yes \
  >"$TEST_TMP/resolve-batch.out"
[ -L "$SEMI_DUP" ] || { echo "批量 + --semi 没把半自动组的副本换成快捷方式"; exit 1; }
[ -f "$SEMI_DUP/SKILL.md" ] || { echo "半自动组的快捷方式读不到内容"; exit 1; }
# 方向是规则的一部分，不是偶然：半自动档的正本必须落在内容更全的那份上（agenta 多一个
# 脚本）。反了就等于把多出来的文件推进回收站、留一份残缺的当源 —— 实测按时间挑就会这样。
case "$(readlink "$SEMI_DUP")" in
  */agenta/skills/gamma-report) ;;
  *) echo "半自动组的正本没落在内容更全的那份上：$(readlink "$SEMI_DUP")"; exit 1 ;;
esac
# 被留下的那份得真的还带着多出来的文件，不然「正本」只是名义上的
[ -f "$SEMI_DUP/scripts/extra.py" ] || { echo "半自动组正本丢了独有文件"; exit 1; }

SEMI_TRASHED=$(find "$FAKE_HOME/.skill-panel/trash" -name gamma-report -type d 2>/dev/null | head -1)
[ -n "$SEMI_TRASHED" ] || { echo "半自动组的原副本没进回收站"; exit 1; }
[ -f "$SEMI_TRASHED/SKILL.md" ] || { echo "回收站里的半自动副本内容不全"; exit 1; }
# 「可还原」这三个字的实底：被换走那一份的独有文件不许凭空消失 —— 要么跟着正本
# 还在原地，要么整份躺在回收站里。正本落哪一边由评分并列时的路径顺序决定，所以
# 这里不断言方向，只断言「东西还在」。
if [ ! -f "$FIXTURE/agenta/skills/gamma-report/scripts/extra.py" ] \
   && [ ! -f "$SEMI_TRASHED/scripts/extra.py" ]; then
  echo "半自动组独有的文件既不在正本也不在回收站里"
  exit 1
fi

grep -q 'gamma-report' "$LEDGER" || { echo "台账没记半自动那一组"; exit 1; }

# ------------------------------------------------- 需人工组：指定正本 → 执行 → 撤销

# 正文已分叉那档的出口。三条必须成立：留哪份由人定；定了工具就把剩下的搬移换链做掉；
# 做完能一键退回去（没有退路的「一键」不该给）。

BETA_CANON="$FIXTURE/agenta/skills/beta-report"
BETA_DUP="$FIXTURE/agentb/skills/beta-report"

# 1) 组外路径必须拒绝。这是唯一的写入口，请求里的路径不能信 —— 否则一个畸形请求就能把
#    任意目录移进回收站、再在原地建一个指向任意位置的快捷方式。
"$PYTHON" "$SCAN" resolve --names beta-report \
  --canonical "beta-report=$FIXTURE/agentb/skills/not-in-this-group" \
  >"$TEST_TMP/resolve-outside.out" 2>&1
grep -q '不属于这一组' "$TEST_TMP/resolve-outside.out" || {
  echo "指定组外路径没被拒绝"; exit 1
}
[ -d "$BETA_DUP" ] && [ ! -L "$BETA_DUP" ] || { echo "被拒绝的请求动了磁盘"; exit 1; }

# 2) 不给正本时必须原地不动 —— 留哪份是人的取舍，工具不替他挑。
"$PYTHON" "$SCAN" resolve --names beta-report >"$TEST_TMP/resolve-manual.out" 2>&1
grep -q '正文已分叉' "$TEST_TMP/resolve-manual.out" || { echo "需人工组没说明为什么不动"; exit 1; }
[ -d "$BETA_DUP" ] && [ ! -L "$BETA_DUP" ] || { echo "需人工组没指定正本就自己动了"; exit 1; }

# 3) 等价写法要能对上。这里用一条父目录软链构造「同一个目录的两种写法」——
#    macOS 的 /tmp→/private/tmp、带软链的家目录都是这一类，实测会误判成「不属于这一组」。
ln -s "$FIXTURE" "$TEST_TMP/fixture-alias"
"$PYTHON" "$SCAN" resolve --names beta-report \
  --canonical "beta-report=$TEST_TMP/fixture-alias/agenta/skills/beta-report" \
  >"$TEST_TMP/resolve-alias.out" 2>&1
grep -q '不属于这一组' "$TEST_TMP/resolve-alias.out" && {
  echo "同一份副本的等价写法被误判成组外路径"; exit 1
}
grep -q '干跑预览' "$TEST_TMP/resolve-alias.out" || { echo "等价写法没进到干跑预览"; exit 1; }
[ -d "$BETA_DUP" ] && [ ! -L "$BETA_DUP" ] || { echo "干跑就动了磁盘"; exit 1; }

# 4) 指定「另一份」（刻意选不是推荐的那一份）。回归：以前 rewrite 是照扫描期的推荐正本算的，
#    用户改选之后，那个列表恰好把用户选中的那份列成待替换对象 —— 于是静默什么都不做。
"$PYTHON" "$SCAN" resolve --names beta-report \
  --canonical "beta-report=$BETA_CANON" --yes >"$TEST_TMP/resolve-manual-yes.out"
[ -L "$BETA_DUP" ] || { echo "指定正本后没把另一份换成快捷方式"; exit 1; }
[ -d "$BETA_CANON" ] && [ ! -L "$BETA_CANON" ] || { echo "被指定为正本的那份反被换掉了"; exit 1; }
[ -f "$BETA_DUP/SKILL.md" ] || { echo "换出来的快捷方式读不到正本内容"; exit 1; }
grep -q '你指定的' "$TEST_TMP/resolve-manual-yes.out" || { echo "没标出这是用户指定的正本"; exit 1; }

# 5) 撤销：先干跑（磁盘不能动），再落盘（磁盘回到去重前）。
"$PYTHON" "$SCAN" undo >"$TEST_TMP/undo-dry.out"
[ -L "$BETA_DUP" ] || { echo "撤销干跑就把快捷方式撤掉了"; exit 1; }
"$PYTHON" "$SCAN" undo --yes >"$TEST_TMP/undo.out"
[ -d "$BETA_DUP" ] && [ ! -L "$BETA_DUP" ] || { echo "撤销后原位没变回实体目录"; exit 1; }
[ -f "$BETA_DUP/SKILL.md" ] || { echo "撤销后内容没回来"; exit 1; }

# 6) 再撤一次 = 往历史里再退一步。同一批不能被撤两遍 —— 台账里每批做完就标了 undone。
#    到这里历史是「alpha → gamma → beta」，撤掉 beta 之后这一步该退到 gamma。
"$PYTHON" "$SCAN" undo --yes >"$TEST_TMP/undo-twice.out" 2>&1
[ -d "$BETA_DUP" ] && [ ! -L "$BETA_DUP" ] || { echo "第二次撤销把已还原的又改回去了"; exit 1; }
grep -q 'gamma-report' "$TEST_TMP/undo-twice.out" || {
  echo "第二次撤销没往历史里退一步（应回到上一次批量）"; exit 1
}
grep -q 'beta-report' "$TEST_TMP/undo-twice.out" && {
  echo "同一批被撤了两遍"; exit 1
}
# 撤到没得撤时是正常结果，不是错误
"$PYTHON" "$SCAN" undo --yes >"$TEST_TMP/undo-empty.out" 2>&1
[ $? -eq 0 ] || { echo "没有可撤销的记录时不该报错退出"; exit 1; }

# ------------------------------------------------- 断链修复，以及它不该解锁的范围

# 断链那一档不需要人指定正本 —— 后面什么都没有，把链指回正本不涉及取舍。这是唯一一条
# 「需人工档里工具自己动手」的例外，所以边界要卡死：有真内容要取舍的一律仍然交人工。

LINK_BROKEN_AT="$FIXTURE/agenta/skills/link-broken"

[ -L "$LINK_BROKEN_AT" ] || { echo "fixture 前提不成立：$LINK_BROKEN_AT 应当是断链"; exit 1; }

"$PYTHON" "$SCAN" resolve --names link-broken >"$TEST_TMP/resolve-linkbroken-dry.out" 2>&1
grep -q '干跑预览' "$TEST_TMP/resolve-linkbroken-dry.out" || {
  echo "断链组没进干跑（这一档不该要求人工指定正本）"; exit 1
}
[ -L "$LINK_BROKEN_AT" ] && [ ! -e "$LINK_BROKEN_AT" ] || { echo "干跑把断链改掉了"; exit 1; }

"$PYTHON" "$SCAN" resolve --names link-broken --yes >"$TEST_TMP/resolve-linkbroken.out" 2>&1
[ -f "$LINK_BROKEN_AT/SKILL.md" ] || { echo "断链没被指回正本"; exit 1; }
# 后面本来什么都没有，所以这次修复不该往回收站搬任何东西
find "$FAKE_HOME/.skill-panel/trash" -name link-broken -type d 2>/dev/null | grep -q . && {
  echo "断链修复不该往回收站搬东西"; exit 1
}
[ -d "$FIXTURE/agentb/skills/link-broken" ] || { echo "正本被动了"; exit 1; }

# 撤销要明说这条不还原，别让人以为撤掉了
"$PYTHON" "$SCAN" undo --yes >"$TEST_TMP/undo-linkbroken.out" 2>&1
grep -q '断链修复' "$TEST_TMP/undo-linkbroken.out" || {
  echo "撤销没说明断链修复不还原"; exit 1
}

# 边界：软链农场（链可能各自指向别处）与「真分叉 + 断链」都必须仍然交人工。
[ -L "$FIXTURE/agenta/skills/link-farm/SKILL.md" ] || {
  echo "fixture 前提不成立：link-farm 里应当只有一条软链"; exit 1
}
for g in link-farm mixed-report; do
  "$PYTHON" "$SCAN" resolve --names "$g" >"$TEST_TMP/resolve-$g.out" 2>&1
  grep -q '正文已分叉' "$TEST_TMP/resolve-$g.out" || { echo "$g 没有交人工"; exit 1; }
done
[ -L "$FIXTURE/agenta/skills/link-farm/SKILL.md" ] || {
  echo "软链农场被自动处理了（换掉就丢了链的映射）"; exit 1
}
[ -f "$FIXTURE/agentb/skills/mixed-report/SKILL.md" ] || {
  echo "真分叉的副本被动了"; exit 1
}

# ------------------------------------------------- 「都先留着」出口

# 有些组没有正确答案：两份都还在正常用，或者权衡之后就是决定先不动。以前没有出口，
# 这些组会永远挂在「待处理」里，数字一直红着，久之就没人看了。

STAT() {
  "$PYTHON" - "$1" <<'PY'
import json, os, sys
d = json.load(open(os.path.expanduser("~/.skill-panel/data/skills.json")))
name = sys.argv[1]
c = next((x for x in d["conflicts"] if x["name"] == name), {})
print(f'{d["stats"].get("todo_manual")} {d["stats"].get("ignored_conflicts")} '
      f'{c.get("ignored")} {(c.get("prescription") or {}).get("grade")}')
PY
}

# 断言失败时打这个，一眼看出是哪个组把数字顶上去的
MANUALS() {
  "$PYTHON" - <<'PY'
import json, os
d = json.load(open(os.path.expanduser("~/.skill-panel/data/skills.json")))
print(" | ".join(f'{c["name"]}:{(c.get("prescription") or {}).get("grade")}'
                 f'{"/ignored" if c.get("ignored") else ""}'
                 for c in d["conflicts"] if (c.get("prescription") or {}).get("grade") == "manual"))
PY
}

# 先重扫一次再取基线：上一段收尾动过文件，拿旧快照当基线会数出别组的差量
"$PYTHON" "$SCAN" scan >/dev/null

# 只认「这一组」的状态与「计数有没有跟着动」，不写死别组带来的绝对数量
before_stat=$(STAT mixed-report)
before_todo=${before_stat%% *}
before_rest=${before_stat#* }
before_manuals=$(MANUALS)
case "$before_rest" in
  "0 False manual") ;;
  *) echo "fixture 前提不成立：mixed-report 应当是待处理里的需人工组（实际：${before_stat}）"; exit 1 ;;
esac

# 名字打错就等于写进一条永远匹配不上的配置，必须拦下
"$PYTHON" "$SCAN" dismiss --names not-a-real-group --yes >"$TEST_TMP/dismiss-bad.out" 2>&1 \
  && { echo "拼错的组名没被拒绝"; exit 1; }

# 干跑不能写盘
"$PYTHON" "$SCAN" dismiss --names mixed-report >"$TEST_TMP/dismiss-dry.out" 2>&1
grep -q 'by_conflict' "$TEST_TMP/dismiss-dry.out" || { echo "「都先留着」缺省不是干跑"; exit 1; }
[ "$(STAT mixed-report)" = "$before_stat" ] || { echo "干跑就写了配置"; exit 1; }

"$PYTHON" "$SCAN" dismiss --names mixed-report --note "两侧都在用" --yes >"$TEST_TMP/dismiss.out" 2>&1
"$PYTHON" "$SCAN" scan >/dev/null
after_stat=$(STAT mixed-report)
after_todo=${after_stat%% *}
after_rest=${after_stat#* }
[ "$after_todo" = "$((before_todo - 1))" ] \
  || { echo "标了「都先留着」之后待人工数没减一（${before_todo} → ${after_todo}）"; \
       echo "  标之前：${before_manuals}"; echo "  标之后：$(MANUALS)"; exit 1; }
case "$after_rest" in
  "1 True none") ;;
  *) echo "标了「都先留着」之后这组仍算待处理（实际：${after_stat}）"; exit 1 ;;
esac
grep -q '两侧都在用' "$SKILL_DIR/overrides.json" || { echo "写的说明没进 overrides.json"; exit 1; }

# 该能随时取消
"$PYTHON" "$SCAN" dismiss --names mixed-report --undo --yes >"$TEST_TMP/undismiss.out" 2>&1
"$PYTHON" "$SCAN" scan >/dev/null
[ "$(STAT mixed-report)" = "$before_stat" ] || { echo "取消标记后没回到待处理"; exit 1; }

# ------------------------------------------------------------------ 单元测试

for suite in test_skillctl.py; do
  "$PYTHON" "$ROOT_DIR/skills/skill-panel/tests/$suite" >"$TEST_TMP/$suite.out" 2>&1 || {
    cat "$TEST_TMP/$suite.out"
    exit 1
  }
  grep -q '^OK' "$TEST_TMP/$suite.out"
done

echo "skill-panel tests passed."
