#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skillctl.py — 本地 skill 面板（扫描家底 + 跨 agent 校验 + 迁移物料 + 原生开关）

设计原则：
  1. 扫描与校验是只读的。写操作（install 生成指令、disable / enable / uninstall）一律
     先干跑打印差量，加 --yes 才落盘；落盘前被替换或删除的东西先进回收站，不真删。
  2. 软链是一等公民。按 realpath 归一化，「条目(entry)」与「唯一实体(entity)」是两个概念。
  3. 校验必须带证据（文件:行号），否则等于没校验。
  4. 判定结果可被 overrides.json 人工纠正。
  5. 只依赖标准库，且必须能在 Python 3.9 上直接跑 —— 别人机器上的 python3 很可能
     就是系统自带的 3.9，注解里不许出现 PEP 604 的 `X | Y`（3.10+ 才有）。
     tests/test_skillctl.py 的 PythonFloorTests 钉住这条。

目录约定：本脚本位于 <skill_root>/scripts/。两类文件分开住 ——

  [通用代码，随 skill 分发]  <skill_root>/
    agents.json / rules.json / overrides.json  声明式配置
    assets/dashboard_template.html             页面模板

  [本地产物，每台机器各自生成]  落点见 artifact_root()
    data/skills.json                           扫描快照
    skill-panel.html                           生成的自包含仪表盘
    plan-<时间戳>.md / .sh                     冲突处理方案包
    trash/  ledger.json                        回收站与操作台账

  产物不写进 skill 目录有三个理由：市场式安装的 skill 目录可能只读；插件升级整目录
  替换，产物会跟着消失；产物含本机路径与命中的凭据原文，本就不该跟着代码走。
  默认落 $HOME/.skill-panel/，用 --out <dir> 或 $SKILL_PANEL_OUT 改。

用法：
  skillctl.py scan                       # 扫描 + 校验 + 写快照与仪表盘
  skillctl.py scan --no-html             # 只写 json
  skillctl.py scan --out /tmp/sp         # 产物换个落点（全局选项，放子命令后面）
  skillctl.py check <skill>              # 终端打印单个 skill 的校验详情
  skillctl.py state <skill>              # 各 agent 的启用状态
  skillctl.py install <skill> --to <agent>   # 终端打印结构化安装指令
  skillctl.py disable|enable <skill> --agent <agent> [--yes]
  skillctl.py uninstall <skill> --agent <agent> [--yes]
  skillctl.py restore                    # 列出回收站
  skillctl.py undo [--yes]                # 撤销上一次一键去重（撤快捷方式、目录搬回原位）
  skillctl.py plan --grades auto,semi,manual
  skillctl.py serve --open               # 直连模式，页面按钮点一下就生效
  skillctl.py agents                     # 列出适配表
"""

import argparse
import glob as globmod
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

# 本脚本住在 <skill_root>/scripts/，配置（agents.json 等）、assets/ 与产物都在上一级。
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 入口脚本所在的目录。页面里所有「可复制命令」都是 `cd <此处> && python3 skillctl.py …`，
# 所以必须是 scripts/ 而不是 skill 根 —— 写错的话页面上每条命令都是死链（曾如此）。
ENTRY_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CURRENT_USER = os.path.basename(HOME)

TEXT_EXT = {
    ".md", ".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".html", ".htm",
    ".css", ".csv", ".tsv", ".sql", ".env", ".template",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}

TOOL_HINTS = [
    ("python3", r"\bpython3\b"), ("python", r"\bpython\b(?!3)"), ("node", r"\bnode\b"),
    ("npx", r"\bnpx\b"), ("pnpm", r"\bpnpm\b"), ("npm", r"\bnpm\b"),
    ("curl", r"\bcurl\b"), ("git", r"\bgit\b"), ("jq", r"\bjq\b"),
    ("ffmpeg", r"\bffmpeg\b"), ("playwright", r"\bplaywright\b"),
    ("wecom-cli", r"\bwecom-cli\b"), ("adhoc", r"\badhoc\b"),
    ("pandoc", r"\bpandoc\b"), ("whisper", r"\bwhisper\b"), ("docker", r"\bdocker\b"),
]


# ---------------------------------------------------------------- 基础工具

def expand(p: str) -> str:
    return os.path.expanduser(p)


def load_json(path: str, default=None):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- 配置校验

KNOWN_ROOT_KINDS = {"user_skills", "shared_pool", "market", "builtin", "plugins"}
KNOWN_WRITERS = {"json_nested", "toml_section", "cli", "filemove"}
KNOWN_GRANULARITIES = {"skill", "plugin", "none"}
KNOWN_VALUE_MODES = {"scalar", "object_field"}


class ConfigError(Exception):
    """agents.json / rules.json 的配置错误。一律硬报错，不静默降级。"""


def validate_agents_config(cfg) -> None:
    """校验 agent 适配表，逐条累积报错后一次性抛出。

    为什么必须硬报错：build_ops 按 writer 分派写入方式，而 JSON 分支是**默认分支** ——
    把 "json_nested" 拼错一个字母不会报错，会静默按 JSON 去写，改到不知哪个文件的键上。
    """
    agents = (cfg or {}).get("agents")
    if not isinstance(agents, list) or not agents:
        raise ConfigError("agents.json 的 agents 必须是非空数组")

    errors, seen = [], set()
    for i, a in enumerate(agents):
        if not isinstance(a, dict):
            errors.append(f"agents[{i}] 不是对象")
            continue
        who = a.get("id") or f"agents[{i}]"
        for key in ("id", "label", "roots"):
            if not a.get(key):
                errors.append(f"{who}: 缺 {key}")
        if a.get("id") in seen:
            errors.append(f"{who}: id 重复")
        seen.add(a.get("id"))
        if isinstance(a.get("supports_symlink"), (dict, list)):
            errors.append(f"{who}: supports_symlink 只能是 true / false / null")

        roots = a.get("roots")
        for j, root in enumerate(roots if isinstance(roots, list) else []):
            if not isinstance(root, dict) or not root.get("path"):
                errors.append(f"{who}: roots[{j}] 缺 path")
                continue
            if root.get("kind") not in KNOWN_ROOT_KINDS:
                errors.append(f"{who}: roots[{j}].kind={root.get('kind')!r} "
                              f"不在 {sorted(KNOWN_ROOT_KINDS)}")

        tg = a.get("toggle")
        if tg is None:
            continue
        if not isinstance(tg, dict):
            errors.append(f"{who}: toggle 必须是对象或 null")
            continue
        gran, writer = tg.get("granularity"), tg.get("writer")
        if gran is not None and gran not in KNOWN_GRANULARITIES:
            errors.append(f"{who}: toggle.granularity={gran!r} "
                          f"不在 {sorted(KNOWN_GRANULARITIES)}")
        if writer is not None and writer not in KNOWN_WRITERS:
            errors.append(f"{who}: toggle.writer={writer!r} 不在 {sorted(KNOWN_WRITERS)}"
                          f" —— 写错不会报错，会静默按 JSON 分支去写")
        if tg.get("value_mode") is not None and tg["value_mode"] not in KNOWN_VALUE_MODES:
            errors.append(f"{who}: toggle.value_mode={tg['value_mode']!r} "
                          f"不在 {sorted(KNOWN_VALUE_MODES)} —— 不认识的值会静默按标量处理")

        if writer == "json_nested" or (writer is None and gran in ("skill", "plugin")):
            for key in ("file", "container"):
                if not tg.get(key):
                    errors.append(f"{who}: toggle 走 JSON 写入，必须给 {key}")
        if writer == "toml_section":
            for key in ("file", "section", "field"):
                if not tg.get(key):
                    errors.append(f"{who}: toggle.writer=toml_section 必须给 {key}")
        if writer == "cli" and not (tg.get("cli") or {}).get("bin"):
            errors.append(f"{who}: toggle.writer=cli 必须给 cli.bin")

    if errors:
        raise ConfigError("agents.json 配置错误：\n  - " + "\n  - ".join(errors))


def validate_rules_config(cfg) -> None:
    """校验规则表。detector 是否真被实现由测试负责，这里只查结构。"""
    rules = (cfg or {}).get("rules")
    if not isinstance(rules, list) or not rules:
        raise ConfigError("rules.json 的 rules 必须是非空数组")

    errors, seen = [], set()
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            errors.append(f"rules[{i}] 不是对象")
            continue
        rid = r.get("id")
        if not rid:
            errors.append(f"rules[{i}] 缺 id")
            continue
        if rid in seen:
            errors.append(f"{rid}: id 重复")
        seen.add(rid)
        if r.get("level") not in ("fail", "warn"):
            errors.append(f"{rid}: level={r.get('level')!r} 只能是 fail 或 warn")
        for key in ("label", "detector"):
            if not r.get(key):
                errors.append(f"{rid}: 缺 {key}")

    if errors:
        raise ConfigError("rules.json 配置错误：\n  - " + "\n  - ".join(errors))


def read_text(path: str, limit: Optional[int] = None) -> str:
    try:
        if limit is not None and os.path.getsize(path) > limit * 4:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(limit)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def parse_frontmatter(text: str):
    """返回 (frontmatter_dict, frontmatter_raw, body)。容错处理，绝不抛异常。

    必须支持 YAML 块标量（`description: >` / `description: |`），
    否则多行描述会被误解析成单个字符，导致「description 过短」大面积假阳性。
    """
    if not text.startswith("---"):
        return {}, "", text
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", text, re.S)
    if not m:
        return {}, "", text
    raw = m.group(1)
    fm = {}
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#") or line[:1] in (" ", "\t"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v in (">", "|", ">-", "|-", ">+", "|+"):
            block, i = [], i + 1
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in (" ", "\t")):
                block.append(lines[i].strip())
                i += 1
            fm[k] = ("\n" if v.startswith("|") else " ").join(
                x for x in block if x).strip()
            continue
        fm[k] = v.strip().strip("\"'")
        i += 1
    return fm, raw, text[m.end():]


def sha(x) -> str:
    b = x.encode("utf-8", "ignore") if isinstance(x, str) else x
    return hashlib.sha256(b).hexdigest()


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0


def find_entity(doc, name, agent_id=None):
    """按名字找实体。同名多份时，若指定了 agent 就优先返回该 agent 持有的那一份，
    否则返回真实副本路径字典序最小的那份（保证结果稳定、可复现）。"""
    if not doc:
        return None
    ents = doc.get("entities") or []
    q = (name or "").strip().lower()
    hits = ([e for e in ents if e["name"].lower() == q]
            or [e for e in ents if e["real_path"].lower() == q]
            or [e for e in ents if q and q in e["name"].lower()])
    if not hits:
        return None
    if agent_id:
        own = [e for e in hits if agent_id in e["agents"]]
        if own:
            hits = own
    return sorted(hits, key=lambda e: e["real_path"])[0]


# ---------------------------------------------------------------- 发现阶段

def _ms_to_iso(ms):
    """毫秒时间戳 → ISO 日期字符串。AutoClaw 的 installedAt 是 epoch ms。"""
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def load_install_manifests(paths):
    """读取各 agent 的 installed_plugins.json，建立 realpath(installPath) -> 元信息 索引。"""
    index = {}
    for p in paths:
        doc = load_json(expand(p))
        if not doc:
            continue
        for key, arr in (doc.get("plugins") or {}).items():
            plugin, _, marketplace = key.partition("@")
            for rec in (arr or []):
                ip = rec.get("installPath")
                if ip:
                    index[os.path.realpath(expand(ip))] = {
                        "plugin": plugin, "marketplace": marketplace,
                        "version": rec.get("version"),
                        "installed_at": rec.get("installedAt"),
                        "scope": rec.get("scope"),
                    }
    return index


def read_plugin_meta(container: str):
    """读取插件清单 plugin.json（bitto / agent-plugins.org 规范形态）。

    向上最多找 3 层，因为内置与市场形态下 SKILL.md 在 skills/<name>/ 内，
    而 plugin.json 在插件根。找不到返回 None。
    """
    cur = container
    for _ in range(3):
        fp = os.path.join(cur, "plugin.json")
        if os.path.isfile(fp):
            doc = load_json(fp)
            if not isinstance(doc, dict):
                return None
            ext = ((doc.get("extensions") or {}).get("bitto") or {})
            author = doc.get("author")
            if isinstance(author, dict):
                author = author.get("name")
            return {
                "manifest_path": fp,
                "id": doc.get("name"),
                "version": doc.get("version"),
                "author": author,
                "display_name": ext.get("displayName"),
                "plugin_kind": ext.get("kind"),
                "has_mcp": os.path.isfile(os.path.join(cur, "mcp.json")),
                "has_agents": os.path.isdir(os.path.join(cur, "agents")),
                "has_commands": os.path.isdir(os.path.join(cur, "commands")),
            }
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def build_builtin_library_index(agents_cfg):
    """把「App 内置库」建成 名称 -> 路径 的索引，只作来源证据，不产出实体。

    为什么只索引不扫描：AutoClaw 的托管目录（~/.openclaw-autoclaw/skills）是
    App 内置库 + 商店元数据生成的投影，实测 44 个里 42 个同名、内容差异仅为
    多出的 _store_meta.json 与 .bundled-hash。两边都扫会凭空产生 42 组假「同名冲突」。
    """
    idx = defaultdict(dict)
    for lib in agents_cfg.get("builtin_libraries", []):
        raw = expand(lib["path"])
        agent = lib.get("for_agent")
        if not agent or not os.path.isdir(raw):
            continue
        for n in sorted(os.listdir(raw)):
            q = os.path.join(raw, n)
            if os.path.isdir(q) and os.path.isfile(os.path.join(q, "SKILL.md")):
                idx[agent][n] = q
    return idx


VERSION_DIR_RE = re.compile(r"^v?\d+(?:\.\d+)*$")


def bundle_of(real_path):
    """尽力识别这个 skill 所属的「上游包名」，用于把同一上游造成的成批冲突归组。

    只有 <X>/skills/<skill> 这种形态才算，且 X 不能是点开头的 agent 自有目录：
      ~/.workbuddy/plugins/cache/<mp>/superpowers/4.0.3/skills/brainstorming → superpowers
      ~/.codex/superpowers/skills/brainstorming                            → superpowers
      ~/.workbuddy/skills/manghe-daily-report                              → None（自有技能）
    """
    parent = os.path.dirname(real_path)
    if os.path.basename(parent) != "skills":
        return None
    up = os.path.dirname(parent)
    seg = os.path.basename(up)
    if not seg or seg.startswith("."):
        return None
    if VERSION_DIR_RE.match(seg):          # 版本目录，包名在再上一层
        up2 = os.path.dirname(up)
        seg2 = os.path.basename(up2)
        return seg2 if seg2 and not seg2.startswith(".") else None
    return seg


def resolve_version(real_path, fm, market_meta):
    """尽力确定该 skill 所属包的版本号，返回 (version, 来源说明)。"""
    if market_meta and market_meta.get("version"):
        src = "技能商店记录" if market_meta.get("via") == "store_meta" else "安装清单"
        return str(market_meta["version"]), src
    base = os.path.dirname(real_path)
    cands = []
    if os.path.basename(base) == "skills":
        cands.append(base)
        up = os.path.dirname(base)
        cands.append(up)
        if VERSION_DIR_RE.match(os.path.basename(up) or ""):
            cands.append(os.path.dirname(up))
    else:
        cur = base
        for _ in range(3):
            nxt = os.path.dirname(cur)
            if not nxt or nxt == cur or nxt == "/":
                break
            cands.append(nxt)
            cur = nxt
    for c in cands:
        fp = os.path.join(c, "package.json")
        if os.path.isfile(fp):
            doc = load_json(fp)
            if isinstance(doc, dict) and doc.get("version"):
                return str(doc["version"]), os.path.relpath(fp, os.path.expanduser("~"))
    if fm.get("version"):
        return str(fm["version"]), "frontmatter"
    return None, None


def iter_entries(agents_cfg, manifest_index):
    """产出原始条目。粒度 = 某个 agent 的某个根下的某个条目。

    返回 (entries, skipped)。skipped 记录「看起来像 skill 但不是」的目录
    （例如只有 plugin.json + mcp.json 的 MCP 插件），供透明审计。
    """
    entries, skipped = [], []
    for agent in agents_cfg.get("agents", []):
        for spec in agent.get("roots", []):
            if isinstance(spec, str):
                spec = {"path": spec, "kind": "user_skills"}
            raw = expand(spec["path"])
            kind = spec.get("kind", "user_skills")
            root_label = spec.get("label") or os.path.basename(raw)
            dedupe = spec.get("dedupe")
            nested = spec.get("nested")
            store_meta = spec.get("store_meta")
            evidence_override = spec.get("evidence")

            if "*" in raw:
                matches = [(os.path.basename(d.rstrip("/")), d)
                           for d in sorted(globmod.glob(raw))]
                is_glob = True
            elif os.path.isdir(raw):
                matches, is_glob = [], False
                for n in sorted(os.listdir(raw)):
                    if n.startswith("."):
                        continue
                    p = os.path.join(raw, n)
                    if os.path.isdir(p) or os.path.islink(p):
                        matches.append((n, p))
            else:
                continue

            # 文件级禁用：没有原生开关的 agent 靠把目录移进 <root>/.disabled/ 来停用。
            # 主循环会跳过点开头目录，所以这里单独捞一遍，让这些条目在清册里
            # 以「已禁用」的身份出现，而不是凭空消失。
            disabled_matches = []
            if not is_glob:
                dis_dir = os.path.join(raw, ".disabled")
                if os.path.isdir(dis_dir):
                    for n2 in sorted(os.listdir(dis_dir)):
                        if n2.startswith("."):
                            continue
                        q2 = os.path.join(dis_dir, n2)
                        if os.path.isdir(q2) or os.path.islink(q2):
                            disabled_matches.append((n2, q2))

            # 容器下钻：plugins/<plugin>/skills/<skill>、skills/<pack>/skills/<skill>
            #
            # 关键：容器自身的 SKILL.md 与内嵌子目录【并列展开】，不是二选一。
            # 实证 —— ~/.bitto/skills/surprise-prize-governance-daily 自己带 SKILL.md，
            # 同时又内嵌 skills/<2 个子技能>；bitto 日志 skill load summary loaded=4
            # 说明三个都装了。旧逻辑二选一会漏掉 2 个子技能。
            if nested:
                expanded = []
                for name_, p_ in matches:
                    pmeta = read_plugin_meta(p_)
                    has_own = os.path.isfile(os.path.join(p_, "SKILL.md"))
                    sub = os.path.join(p_, nested)
                    subs = []
                    if os.path.isdir(sub):
                        for n2 in sorted(os.listdir(sub)):
                            if n2.startswith("."):
                                continue
                            q = os.path.join(sub, n2)
                            if os.path.isdir(q) or os.path.islink(q):
                                subs.append((n2, q))
                    if has_own:
                        expanded.append((name_, p_, root_label, "root", pmeta))
                    for n2, q in subs:
                        expanded.append((n2, q, f"{root_label}·{name_}", "nested", pmeta))
                    if not has_own and not subs:
                        skipped.append({"agent": agent["id"], "path": p_,
                                        "reason": "既无 SKILL.md 也无嵌套 skills/，判定为非 skill 载体"
                                                  "（如只有 plugin.json + mcp.json 的 MCP 插件）"})
                matches = [(n, p, lv, pm) for n, p, _, lv, pm in expanded]
                labels = {p: lb for _, p, lb, _, _ in expanded}
            else:
                matches = [(n, p, "plain", None) for n, p in matches]
                labels = {p: root_label for _, p, _, _ in matches}

            all_matches = [(n, p, lv, pm, False) for n, p, lv, pm in matches]
            for n2, q2 in disabled_matches:
                all_matches.append((n2, q2, "plain", read_plugin_meta(q2), True))

            for name, p, nested_level, pmeta, file_disabled in all_matches:
                if is_glob and (name.startswith(".")
                                or not (os.path.isdir(p) or os.path.islink(p))):
                    continue
                is_link = os.path.islink(p)
                real = os.path.realpath(p)
                meta = None
                store_rec = None
                if store_meta:
                    doc = load_json(os.path.join(p, store_meta))
                    if isinstance(doc, dict) and doc.get("source"):
                        store_rec = {
                            "skill_id": doc.get("skillId"),
                            "skill_key": doc.get("skillKey"),
                            "version": doc.get("version"),
                            "source": doc.get("source"),
                            "installed_at_ms": doc.get("installedAt"),
                            "file": store_meta,
                        }
                eff_kind = kind
                eff_label = labels.get(p, root_label)
                if dedupe == "manifest":
                    # <cache>/<marketplace>/<plugin>/<version>/skills/<skill>
                    # 从 skill 目录上溯两层即 installPath（版本根）
                    ver_root = os.path.realpath(os.path.dirname(os.path.dirname(p)))
                    meta = manifest_index.get(ver_root)
                    if not meta:
                        continue
                    eff_label = f"{root_label}·{meta['plugin']}"
                    if str(meta.get("marketplace", "")).endswith("builtin"):
                        eff_kind = "builtin"
                entries.append({
                    "agent": agent["id"], "agent_label": agent["label"],
                    "root": raw, "root_kind": eff_kind, "root_label": eff_label,
                    "name": name, "path": p, "is_link": is_link,
                    "link_raw": os.readlink(p) if is_link else None,
                    "real_path": real, "exists": os.path.isdir(real),
                    "nested_level": nested_level, "plugin_meta": pmeta,
                    "store_record": store_rec, "evidence_override": evidence_override,
                    "file_disabled": file_disabled,
                })
    return entries, skipped


def classify_type(real_path, root_kind, manifest_index, market_meta,
                  lib_hit=None, evidence_override=None):
    """来源可验证的类型判定：builtin / market / local。"""
    if market_meta:
        if market_meta.get("via") == "store_meta":
            return "market", (f"命中技能商店安装记录 {market_meta['plugin']} "
                              f"v{market_meta.get('version')}（skillId "
                              f"{str(market_meta.get('skill_id'))[:8]}…）"), market_meta
        return "market", (f"命中安装清单 {market_meta['plugin']}@"
                          f"{market_meta['marketplace']} v{market_meta['version']}"), market_meta
    if evidence_override:
        return root_kind, evidence_override, None
    if root_kind == "builtin":
        return "builtin", "位于 agent 的系统内置目录", None
    if root_kind == "market":
        return "market", "位于市场插件缓存目录", None
    if root_kind == "plugins":
        return "local", ("位于 agent 的 plugins/ 载体。bitto 无安装清单，"
                         "「市场安装」与「自建」无法自动区分（来源看 plugin.json 的 author）"), None
    if root_kind == "shared_pool":
        return "local", "位于共享池（用户自建，被多 agent 引用）", None
    if lib_hit:
        # 无商店记录，但 App 内置库里存在同名技能 → 判为内置（升级 App 会被覆盖）
        return "builtin", (f"无安装记录，但 App 内置库中存在同名技能（{lib_hit}）"
                           f" —— 判为内置来源"), None
    return "local", "位于用户 skills 目录且无安装记录", None


def scan_entity_files(root: str, budget: int):
    files, text_files, total_bytes, total_lines = [], [], 0, 0
    consumed = 0
    truncated = False
    # 真文件 / 软链分开数，再取真实文件里最晚的 mtime。
    # 「目录里全是软链」（软链农场）和「最近被动过」都靠这几个数，别再从 file_count 反推 ——
    # 软链在下面按 size=0 记账，混在一起就分不出「空目录」和「只有软链的目录」。
    real_files = link_files = broken_links = 0
    mtime = 0.0
    if not os.path.isdir(root):
        return {"files": [], "text_files": [], "total_bytes": 0, "file_count": 0,
                "line_count": 0, "truncated": False,
                "real_file_count": 0, "link_file_count": 0, "broken_link_count": 0,
                "mtime": 0.0}
    for dp, dns, fns in os.walk(root, followlinks=False):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in sorted(fns):
            fp = os.path.join(dp, fn)
            rel = os.path.relpath(fp, root)
            if os.path.islink(fp):
                link_files += 1
                if not os.path.exists(fp):
                    broken_links += 1
                files.append({"rel": rel, "link": True,
                              "broken": not os.path.exists(fp), "size": 0})
                continue
            try:
                size = os.path.getsize(fp)
            except OSError:
                continue
            files.append({"rel": rel, "link": False, "broken": False, "size": size})
            real_files += 1
            total_bytes += size
            try:
                m = os.path.getmtime(fp)
            except OSError:
                pass
            else:
                if m > mtime:
                    mtime = m
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT or size > 2_000_000:
                continue
            if consumed >= budget:
                truncated = True
                continue
            content = read_text(fp)
            consumed += len(content)
            lines = content.split("\n")
            total_lines += len(lines)
            text_files.append({"rel": rel, "lines": lines})
    return {"files": files, "text_files": text_files, "total_bytes": total_bytes,
            "file_count": len(files), "line_count": total_lines, "truncated": truncated,
            "real_file_count": real_files, "link_file_count": link_files,
            "broken_link_count": broken_links, "mtime": mtime}


# ---------------------------------------------------------------- 检测器

def det_regex_lines(rule, root, scan):
    pats = [re.compile(p, re.I) for p in rule.get("patterns", [])]
    allows = [re.compile(p, re.I) for p in rule.get("allow_patterns", [])]
    hits, seen = [], set()
    for tf in scan["text_files"]:
        for i, line in enumerate(tf["lines"], 1):
            if len(line) > 400 or any(a.search(line) for a in allows):
                continue
            for pat in pats:
                m = pat.search(line)
                if m:
                    key = (tf["rel"], i)
                    if key not in seen:
                        seen.add(key)
                        hits.append({"file": tf["rel"], "line": i,
                                     "text": line.strip()[:180], "match": m.group(0)[:60]})
                    break
    return hits


DOC_DIRS = {"references", "reference", "docs", "doc", "examples", "example",
            "assets", "samples", "sample", "cases"}
EXAMPLE_LINE_RE = re.compile(
    r"(?i)\be\.g\.|\bexample\b|\beg\.\b|例如|示例|比如|举例|\bfor instance\b|\bsuch as\b")

ABS_PATH_RE = re.compile(r"(?:/Users/([A-Za-z0-9_.\-]+)|/home/([A-Za-z0-9_.\-]+))")
PLACEHOLDER_USER_RE = re.compile(
    r"^(?:\.{2,}.*|-+|_+|x{3,}|name|user|username|you|yourname|youruser|me|someone|"
    r"placeholder|example|foo|bar|bob|alice|jesse|test|admin)$", re.I)
PLACEHOLDER_LINE_RE = re.compile(
    r"<[^>]{1,60}>|\$\{|\$[A-Z_]{2,}|%[A-Za-z_]+%|\{\{|xxx+|\byour[-_]|\bfoobar\b")


def det_foreign_abs_path(rule, root, scan):
    """检出指向「别人机器/别的用户」的绝对路径。

    必须排除占位符：`/Users/.../`、`/Users/name/`、`/Users/<user>/` 这类是文档示例，
    不是真的死路径，否则会淹没真阳性。
    """
    extra_ph = {u.lower() for u in rule.get("placeholder_users", [])}
    hits = []
    for tf in scan["text_files"]:
        for i, line in enumerate(tf["lines"], 1):
            if PLACEHOLDER_LINE_RE.search(line):
                continue
            for m in ABS_PATH_RE.finditer(line):
                who = m.group(1) or m.group(2)
                if not who or who == CURRENT_USER:
                    continue
                if PLACEHOLDER_USER_RE.match(who) or who.lower() in extra_ph:
                    continue
                hits.append({"file": tf["rel"], "line": i,
                             "text": line.strip()[:180], "match": m.group(0)})
    return hits


def det_local_abs_path(rule, root, scan):
    pat = re.compile(r"/Users/" + re.escape(CURRENT_USER) + r"/")
    hits = []
    for tf in scan["text_files"]:
        for i, line in enumerate(tf["lines"], 1):
            if pat.search(line):
                hits.append({"file": tf["rel"], "line": i, "text": line.strip()[:180],
                             "match": f"/Users/{CURRENT_USER}/"})
    return hits


SCRIPT_REF_RE = re.compile(
    r"(?:\./)?((?:scripts?|bin|tools?)/[A-Za-z0-9_\-./*]+\.[A-Za-z0-9*]{1,5})")
# 只有当引用出现在「命令上下文」里才算数。散文里提到的 `scripts/foo.py`（如
# "A `scripts/rotate_pdf.py` helper would be helpful"）不是真引用，否则全是假阳性。
INVOKE_RE = re.compile(
    r"(?i)\b(?:python3?|node|npx|bash|zsh|bun|deno|ruby|perl|pwsh|powershell|sh)\b|\./")
OTHER_SKILL_PATH_RE = re.compile(
    r"~/\.(?:workbuddy|claude|codex|agents|minimax|bitto)/skills|plugin[ _]?root|plugin 根|"
    r"skill[ _]?root|skill 根|basedir|base dir|\bcd\b")


def det_broken_script_ref(rule, root, scan):
    """检出「文档里引用了脚本、但磁盘上没有」。

    降噪四道闸：
      1. 跳过含占位符/变量的行（`<plugin_root>/scripts/x.py`、`${CLAUDE_PLUGIN_ROOT}`）
      2. 跳过示例语气（e.g. / Example / 例如）与跨目录引用（`../`、指向别的 skill 根）
      3. 要求 skill 内确实存在该顶层目录（scripts/ 或 bin/）
      4. 要求引用出现在命令上下文里（python3/node/bash/./ 等）
    """
    fileset = {f["rel"] for f in scan["files"]}
    base_set = {f.split("/")[-1] for f in fileset}
    top_dirs = {rel.split("/")[0] for rel in fileset if "/" in rel}
    hits, seen = [], set()
    for tf in scan["text_files"]:
        if tf["rel"] != "SKILL.md":
            continue
        for i, line in enumerate(tf["lines"], 1):
            if (PLACEHOLDER_LINE_RE.search(line) or EXAMPLE_LINE_RE.search(line)
                    or OTHER_SKILL_PATH_RE.search(line) or "../" in line
                    or not INVOKE_RE.search(line)):
                continue
            for m in SCRIPT_REF_RE.finditer(line):
                ref = m.group(1)
                if "*" in ref or ref.startswith("../") or "/../" in ref:
                    continue
                if ref.split("/")[0] not in top_dirs:
                    continue
                if ref in seen:
                    continue
                seen.add(ref)
                if ref in fileset or ref.split("/")[-1] in base_set:
                    continue
                hits.append({"file": tf["rel"], "line": i,
                             "text": line.strip()[:180], "match": ref})
    return hits


def det_broken_symlink(rule, root, scan):
    return [{"file": f["rel"], "line": 0, "text": "软链目标已不存在", "match": f["rel"]}
            for f in scan["files"] if f["link"] and f["broken"]]


# ---------------------------------------------------------------- 实体构建

def detect_deps(ctx, scan):
    deps = {"tools": [], "skills": [], "mcp": []}
    fm = ctx["fm"]
    for key in ("requires", "dependencies", "depends_on"):
        v = fm.get(key)
        if v:
            deps["skills"] += [x.strip() for x in re.split(r"[,\[\]\s]+", v) if x.strip()]
    blob = "\n".join(l for tf in scan["text_files"][:6] for l in tf["lines"][:400])
    for label, pat in TOOL_HINTS:
        if re.search(pat, blob):
            deps["tools"].append(label)
    if re.search(r"\bmcp\b|mcp__", blob, re.I):
        deps["mcp"].append("提及 MCP")
    deps["tools"] = sorted(set(deps["tools"]))
    deps["skills"] = sorted(set(deps["skills"]))
    return deps


def build_entities(entries, agents_cfg, rules_cfg, overrides, manifest_index,
                   builtin_lib_index=None, toggle_snap=None):
    th = rules_cfg.get("thresholds", {})
    budget = th.get("text_read_budget_bytes", 400_000)
    ev_max = th.get("evidence_max_per_rule", 5)
    oversize = th.get("oversize_text_bytes", 204_800)
    short_desc = th.get("short_description_chars", 30)

    by_real = defaultdict(list)
    for e in entries:
        by_real[e["real_path"]].append(e)

    rules = [r for r in rules_cfg.get("rules", []) if r.get("enabled", True)]
    entity_rules = [r for r in rules if r.get("scope", "entity") == "entity"]
    install_rules = [r for r in rules if r.get("scope") == "install"]

    entities = []
    for real_path, refs in by_real.items():
        refs = sorted(refs, key=lambda x: (x["agent"], x["path"]))
        owned = [r for r in refs if not r["is_link"]] or refs
        primary = owned[0]
        name = primary["name"]
        root_kind = primary["root_kind"]
        nested_level = primary.get("nested_level", "plain")
        scan = scan_entity_files(real_path, budget)

        skill_md = os.path.join(real_path, "SKILL.md")
        has_skill_md = os.path.isfile(skill_md)
        fm, fm_raw, body = ({}, "", "")
        if has_skill_md:
            fm, fm_raw, body = parse_frontmatter(read_text(skill_md))

        market_meta = None
        for r in owned:
            if r["root_kind"] in ("market", "builtin"):
                for vroot, meta in manifest_index.items():
                    if real_path.startswith(vroot + os.sep):
                        market_meta = meta
                        break
            if market_meta:
                break

        # 技能商店安装记录（如 AutoClaw 的 _store_meta.json）：无安装清单时的替代证据，
        # 且比清单更细 —— 它逐技能给出 skillId / version / installedAt。
        store_record = next((r.get("store_record") for r in owned if r.get("store_record")), None)
        if not market_meta and store_record:
            market_meta = {
                "plugin": store_record.get("skill_key") or name,
                "marketplace": "AutoClaw 技能商店",
                "version": store_record.get("version"),
                "installed_at": _ms_to_iso(store_record.get("installed_at_ms")),
                "skill_id": store_record.get("skill_id"),
                "via": "store_meta",
            }

        lib_hit = None
        if builtin_lib_index:
            lib_hit = (builtin_lib_index.get(primary["agent"]) or {}).get(name)

        etype, tevidence, market_meta = classify_type(
            real_path, root_kind, manifest_index, market_meta,
            lib_hit=lib_hit,
            evidence_override=next((r.get("evidence_override") for r in owned
                                    if r.get("evidence_override")), None))
        auto_created = str(fm.get("agent_created", "")).strip().lower() in ("true", "yes", "1")

        # 技能集合目录：自身没有 SKILL.md，但内部有多个带 SKILL.md 的子技能
        # （例如 ~/.agents/skills/superpowers → 一个挂载进来的技能集合）。
        # 它不是"缺 SKILL.md"，只是容器，不该按缺陷计。
        child_skill_count = 0
        if not has_skill_md and os.path.isdir(real_path):
            try:
                for n in os.listdir(real_path):
                    q = os.path.join(real_path, n)
                    if os.path.isdir(q) and os.path.isfile(os.path.join(q, "SKILL.md")):
                        child_skill_count += 1
            except OSError:
                pass
        is_container = not has_skill_md and child_skill_count >= 2

        body_hash = sha(re.sub(r"^---.*?---", "", read_text(skill_md), count=1, flags=re.S)) \
            if has_skill_md else None
        full_hash = sha("|".join(f"{f['rel']}:{f['size']}" for f in scan["files"])
                        + "|" + (body_hash or ""))

        ctx = {"name": name, "root": real_path, "scan": scan, "fm": fm, "body": body,
               "has_skill_md": has_skill_md, "skill_md": skill_md,
               "description": fm.get("description") or None}

        checks = []
        for rule in entity_rules:
            det = rule["detector"]
            try:
                if det == "missing_skill_md":
                    ev = [{"file": "-", "line": 0, "text": "目录内无 SKILL.md", "match": ""}] \
                        if (not has_skill_md and not is_container) else []
                elif det == "empty_dir":
                    ev = [{"file": "-", "line": 0, "text": "目录内没有任何文件", "match": ""}] \
                        if (scan["file_count"] == 0 and not is_container) else []
                elif det == "missing_frontmatter":
                    ev = [{"file": "SKILL.md", "line": 1, "text": "开头没有 YAML frontmatter", "match": ""}] \
                        if (has_skill_md and not fm) else []
                elif det == "missing_name":
                    ev = [{"file": "SKILL.md", "line": 1, "text": "frontmatter 缺 name", "match": ""}] \
                        if (has_skill_md and not fm.get("name")) else []
                elif det == "missing_description":
                    ev = [{"file": "SKILL.md", "line": 1, "text": "frontmatter 缺 description", "match": ""}] \
                        if (has_skill_md and not fm.get("description")) else []
                elif det == "regex_lines":
                    ev = det_regex_lines(rule, real_path, scan)
                elif det == "foreign_abs_path":
                    ev = det_foreign_abs_path(rule, real_path, scan)
                elif det == "local_abs_path":
                    ev = det_local_abs_path(rule, real_path, scan)
                elif det == "broken_script_ref":
                    ev = det_broken_script_ref(rule, real_path, scan)
                elif det == "broken_symlink":
                    ev = det_broken_symlink(rule, real_path, scan)
                elif det == "oversize_text":
                    ev = [{"file": "-", "line": 0,
                           "text": f"文本体量 {human_bytes(scan['total_bytes'])}，"
                                   f"超过阈值 {human_bytes(oversize)}", "match": ""}] \
                        if scan["total_bytes"] > oversize else []
                elif det == "short_description":
                    d = ctx["description"] or ""
                    ev = [{"file": "SKILL.md", "line": 0,
                           "text": f"description 仅 {len(d)} 字符：{d[:90]}", "match": ""}] \
                        if (has_skill_md and d and len(d) < short_desc) else []
                elif det == "name_dir_mismatch":
                    # bitto 装载器会对此发警告（实测日志）：
                    #   skill load warning path=.../SKILL.md name "xxx" does not match parent directory "yyy"
                    # 技能仍能加载，不阻塞迁移，但迁到别的 agent 会带着同样的告警。
                    ev = []
                    val = str(fm.get("name") or "").strip()
                    parent = os.path.basename(real_path.rstrip("/"))
                    if has_skill_md and val and val != parent:
                        if parent.endswith(val):
                            pattern = "目录名 = 前缀 + name（成批套壳）"
                        elif val.endswith(parent) or parent.endswith(val.replace("_", "-")):
                            pattern = "命名风格差异"
                        else:
                            pattern = "完全不一致"
                        ln = 0
                        for tf in scan["text_files"]:
                            if tf["rel"] == "SKILL.md":
                                for i, line in enumerate(tf["lines"], 1):
                                    if re.match(r"\s*name\s*:", line):
                                        ln = i
                                        break
                                break
                        ev = [{"file": "SKILL.md", "line": ln,
                               "text": f'name="{val}" ≠ 目录名 "{parent}"（{pattern}）',
                               "match": val}]
                elif det == "plugin_root_skill_md":
                    # 实证：~/.bitto/plugins/rain-meeting-summary 把 SKILL.md 放在插件根、
                    # 没有 skills/ 子目录，bitto 日志报
                    #   failed to load installed plugin plugin_id="rain-meeting-summary"
                    ev = [{"file": "SKILL.md", "line": 1,
                           "text": "SKILL.md 直接放在插件根、没有 skills/ 子目录；"
                                   "bitto 插件装载校验会拒绝（实测 rain-meeting-summary 装载失败）",
                           "match": ""}] \
                        if (root_kind in ("plugins", "builtin") and nested_level == "root") else []
                elif det == "missing_plugin_json":
                    # bitto 形态是 plugins/<plugin>/skills/<skill>，plugin.json 在插件根，
                    # 所以要向上最多找两层，不能只看 skill 目录本身。
                    found = False
                    cur = real_path
                    for _ in range(3):
                        if os.path.isfile(os.path.join(cur, "plugin.json")):
                            found = True
                            break
                        parent = os.path.dirname(cur)
                        if parent == cur:
                            break
                        cur = parent
                    ev = [{"file": "-", "line": 0,
                           "text": "plugins 载体（含上级）均无 plugin.json", "match": ""}] \
                        if (root_kind == "plugins" and not found) else []
                else:
                    ev = []
            except Exception as exc:
                ev = [{"file": "-", "line": 0, "text": f"规则执行异常：{exc}", "match": ""}]
            if ev:
                checks.append({"id": rule["id"], "level": rule["level"],
                               "kind": rule.get("kind", "other"), "label": rule["label"],
                               "desc": rule.get("desc", ""), "count": len(ev),
                               "evidence": ev[:ev_max], "evidence_truncated": len(ev) > ev_max})

        # 文档目录降级：SKILL.md 里的死路径会让 agent 照着跑并失败；
        # references/ docs/ examples/ 里的路径多半是资料摘录，不该阻塞迁移。
        for c in checks:
            if c["level"] != "fail" or not c["evidence"]:
                continue
            dirs = {ev["file"].split("/")[0] for ev in c["evidence"] if "/" in ev["file"]}
            if dirs and dirs <= DOC_DIRS:
                c["level"] = "warn"
                c["desc"] = c["desc"] + "（命中均在文档/示例目录，已降级为提示）"

        ov = None
        for key in (name, real_path):
            if key in (overrides.get("by_entity") or {}):
                ov = overrides["by_entity"][key]
                break
        override_applied = []
        override_note = None
        if ov:
            if ov.get("note"):
                override_note = ov["note"]
            if ov.get("type"):
                etype = ov["type"]
                tevidence = "人工覆盖：" + tevidence
                override_applied.append("type")
            if "auto_created" in ov:
                auto_created = bool(ov["auto_created"])
                override_applied.append("auto_created")
            if ov.get("ignore_rules"):
                keep = []
                for c in checks:
                    if c["id"] in ov["ignore_rules"]:
                        override_applied.append(f"忽略:{c['id']}")
                    else:
                        keep.append(c)
                checks = keep

        fails = [c for c in checks if c["level"] == "fail"]
        warns = [c for c in checks if c["level"] == "warn"]
        verdict = "fail" if fails else ("warn" if warns else "pass")

        # 版本：用于识别「同一上游包在不同 agent 里版本不一致」这类静默漂移
        ver, ver_src = resolve_version(real_path, fm, market_meta)

        # ---- 启用状态：按 agents.json 的声明逐 agent 解析原生开关 ----
        agents_index = {a["id"]: a for a in agents_cfg.get("agents", [])}
        pkey, _pname = plugin_key_of(real_path)
        proxy = {"real_path": real_path, "fm_name": fm.get("name")}
        ref_objs = []
        for r in refs:
            ro = {
                "agent": r["agent"], "agent_label": r["agent_label"], "path": r["path"],
                "is_link": r["is_link"], "link_raw": r["link_raw"],
                "exists": r["exists"], "root_label": r["root_label"],
                "plugin_key": pkey, "overlay_key": overlay_key_of(proxy),
                "file_disabled": bool(r.get("file_disabled")),
                "state": STATE_NA, "state_known": False,
                "state_source": "", "state_label": "无开关记录",
            }
            ag = agents_index.get(r["agent"])
            if ag:
                st, known, src = resolve_agent_state(ag, proxy, ro, toggle_snap or {})
                ro["state"], ro["state_known"] = st, known
                ro["state_source"] = src
                ro["state_label"] = state_label(ag, st)
            ref_objs.append(ro)

        states = {r["agent"]: r["state"] for r in ref_objs}
        off_agents = sorted(a for a, s in states.items() if s == "off")
        model_off_agents = sorted(a for a, s in states.items() if s == "model_off")
        unknown_state_agents = sorted(a for a, s in states.items()
                                      if s in (STATE_UNKNOWN, STATE_NA))
        # 实体级状态：只要有任何一个持有方禁用，就算这条记录已停用
        if off_agents and len(off_agents) == len(states):
            overall_state = "off"
        elif off_agents:
            overall_state = "partial_off"
        elif model_off_agents and len(model_off_agents) == len(states):
            overall_state = "model_off"
        elif model_off_agents:
            overall_state = "partial_model_off"
        else:
            overall_state = "on"

        entities.append({
            "name": name, "real_path": real_path,
            "fm_name": fm.get("name"),
            "type": etype, "type_evidence": tevidence, "auto_created": auto_created,
            "overrides_applied": override_applied, "override_note": override_note,
            "market_meta": market_meta,
            "root_kind": root_kind, "root_label": primary["root_label"],
            "nested_level": primary.get("nested_level", "plain"),
            "plugin_meta": primary.get("plugin_meta"),
            "plugin_key": pkey,
            "container": is_container, "child_skill_count": child_skill_count,
            "description": (fm.get("description") or "")[:300],
            "description_zh": (fm.get("description_zh") or "")[:300],
            "version": ver, "version_source": ver_src, "fm_version": fm.get("version"),
            "author": fm.get("author"),
            "bundle": bundle_of(real_path),
            "from_builtin_library": bool(lib_hit), "library_path": lib_hit,
            "store_record": store_record,
            "refs": ref_objs,
            "agents": sorted({r["agent"] for r in refs}),
            "entity_agents": sorted({r["agent"] for r in refs if not r["is_link"]}),
            "link_agents": sorted({r["agent"] for r in refs if r["is_link"]}),
            "link_count": sum(1 for r in refs if r["is_link"]),
            "entity_count": sum(1 for r in refs if not r["is_link"]),
            "states": states, "overall_state": overall_state,
            "off_agents": off_agents, "model_off_agents": model_off_agents,
            "unknown_state_agents": unknown_state_agents,
            "external_link": any(r["is_link"] and not r["real_path"].startswith(
                os.path.realpath(expand("~/.agents")) + os.sep) for r in refs),
            "file_count": scan["file_count"], "total_bytes": scan["total_bytes"],
            "line_count": scan["line_count"], "truncated": scan["truncated"],
            # 真文件 / 软链分开记：冲突页要靠它区分「空目录」「只有软链的目录」「真有内容」，
            # 也靠 mtime 说「这份最近被动过」。软链按 size=0 记账，只看 file_count 是分不出来的。
            "real_file_count": scan["real_file_count"],
            "link_file_count": scan["link_file_count"],
            "broken_link_count": scan["broken_link_count"],
            "mtime": scan["mtime"],
            "path_exists": os.path.exists(real_path),
            # 断链：这副「实体」其实只是一条指向空气的快捷方式，real_path 是它指向的那个不
            # 存在的目标，于是「这条链待在哪儿」的信息会丢 —— 想把它指回正本就没处下手。
            # 所以单独记下落在什么地方。路径不存在时它才有值。
            "link_at": (sorted(r["path"] for r in refs if r["is_link"])
                        if not os.path.exists(real_path) else []),
            "body_hash": body_hash, "full_hash": full_hash,
            "checks": checks, "fail_count": len(fails), "warn_count": len(warns),
            "verdict": verdict, "deps": detect_deps(ctx, scan),
        })
    return entities, install_rules


# ---------------------------------------------------------------- 冲突分析

def classify_nature(group):
    """同名 ≠ 重复。先分清「真重复」与「同名异物」，这一步决定了要不要动手。

    实测 48 组里只有 28 组该处理，另外 20 组是巧合同名：
      · skill-creator / pdf / docx / pptx —— 各 App 各自自带的内置技能恰好重名
      · superpowers 全家桶 —— 同一上游包在 Codex 与 WorkBuddy 两个分发渠道各一份
    把它们当重复合并会出事：内置那份会被 App 升级覆盖，两个渠道合并会让一侧的升级链路失效。
    """
    types = {e["type"] for e in group}
    pkeys = {e.get("plugin_key") for e in group}
    if types == {"builtin"}:
        return "coexist", "各 App 自带的内置技能恰好重名，来源互不相干"
    if "builtin" in types:
        return "coexist", "一方是 App 自带、另一方是用户/市场副本，不是同一份东西的复制"
    if types == {"market"} and len(pkeys) > 1:
        return "coexist", "同一上游包在不同分发渠道各存一份，两边各自随自己的渠道升级"
    return "duplicate", "同一份内容被复制到了多处，属于真正的副本漂移"


def _short_time(ts):
    """把 mtime 说成人话。取不到就返回 —，不抛异常。"""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (OSError, OverflowError, ValueError, TypeError):
        return "—"


def canonical_blocked(x):
    """这份副本能不能当正本。返回不能的理由，空串表示可以。

    挡掉的三类都是「执行下去会出事」：
      · 路径不存在 —— 断链。实测 `~/.agents/skills/find-skills` 正是这样被选成正本的，
        照着它执行就会把好副本换成指向空气的快捷方式。
      · 目录里没有真实文件 —— 空壳，或整个目录只有软链（软链农场）。
      · 来自技能商店 / App 内置 —— 渠道升级会把整个目录换掉，正本放这儿等于给以后埋断链。
    """
    if not x.get("path_exists", True):
        return "路径不存在（快捷方式断了）"
    if not x.get("real_file_count"):
        if x.get("link_file_count"):
            return "目录里全是快捷方式，没有自己的文件"
        return "目录里没有文件"
    if x.get("type") == "market":
        return "来自技能商店，升级时会被整个换掉"
    if x.get("type") == "builtin":
        return "App 内置技能，升级 App 会被覆盖"
    return ""


def candidate_usable(x):
    """这份副本能不能当**推荐**的正本。返回 (可用, 不能用的原因)。

    比 canonical_blocked 多挡一条：已被停用的副本不推荐。
    但人在页面上明确指定时允许 —— 你可能就是想以它为准，只是在某个 agent 下关掉了它。
    """
    why = canonical_blocked(x)
    if why:
        return False, why
    if (x.get("state") or "") in ("off", "model_off"):
        return False, "已被停用"
    return True, ""


def canonical_rank(x, mode="stable"):
    """可用候选的排序。三种规则，按「这一组到底是什么问题」选：

    · time（正文已分叉）：只有「哪份是你后来改的」能说明问题 —— 本机实测 32 份冲突副本里
      状态不是启用的只有 3 份、引用数为 0 的有 28 份、版本号 21 份没有，这三个信号里只有
      时间既有区分度又讲得清楚。
    · content（正文一致但文件集不同）：这一档要留的必须是**内容更全**的那份。按时间挑会挑中
      「更晚被复制过来」的那一份，把它定成正本等于拿残缺的当源、把多出来的文件推进回收站。
    · stable（内容逐字一致）：留哪份都不改内容，优先留在已被多方引用的那份 —— 正本放在只有
      单个 agent 看得见的角落，等于让别的 agent 都绕过它。刻意不看 mtime：内容一样时「更晚」
      往往只是「更晚被复制过来」，拿它当判据会让同一份家底在不同机器上挑出不同正本。

    并列时取路径短的兜底。兜底是任意的，所以页面上会把选中的那份显示出来，点之前能看清。
    """
    if mode == "time":
        return (float(x.get("mtime") or 0), int(x.get("link_count") or 0),
                -len(x["real_path"]))
    if mode == "content":
        return (int(x.get("real_file_count") or 0), int(x.get("total_bytes") or 0),
                int(x.get("link_count") or 0), -len(x["real_path"]))
    shared = str(x["real_path"]).startswith(os.path.join(HOME, ".agents", "skills") + os.sep)
    return (int(x.get("link_count") or 0), 1 if shared else 0, -len(x["real_path"]))


def canonical_note(x, others, mode="stable"):
    """推荐它的理由。只说人话 —— 不出现评分、相似度这类词。

    理由要跟真正的排序依据一致：按时间挑的就别说「它被引用得多」，反之亦然 ——
    说一个没参与判断的理由，等于教人用错的判据。
    """
    bits = []
    if mode == "time":
        mine, top = float(x.get("mtime") or 0), max(
            [float(o.get("mtime") or 0) for o in others] or [0.0])
        if mine and mine >= top:
            bits.append(f"最近被动过（{_short_time(mine)}）")
    if mode == "content":
        mine = int(x.get("real_file_count") or 0)
        top = max([int(o.get("real_file_count") or 0) for o in others] or [0])
        if mine > top:
            bits.append(f"文件最全（{mine} 个，另一份只有 {top} 个）"
                        if top else f"文件最全（{mine} 个）")
    if x.get("link_count"):
        bits.append(f"已被 {x['link_count']} 处快捷方式引用")
    if str(x["real_path"]).startswith(os.path.join(HOME, ".agents", "skills") + os.sep):
        bits.append("落在跨 agent 共享池，天然被多方引用")
    if x.get("entity_agents"):
        bits.append(f"是实体本体（{','.join(x['entity_agents'][:2])} 直接持有）")
    return "；".join(bits[:2]) or "候选里其他几份要么更旧、要么已经被停用"


SHAPE_LABEL = {
    "broken": "有一份坏了",
    "symlink-farm": "有一份只剩快捷方式",
    "shell": "有一份疑似转发壳",
    "fork": "正文各有改动",
}
SHAPE_SENTENCE = {
    "broken": "有一份的路径已经不存在了 —— 那不是「两份内容不一样」，是那一份本身坏了。",
    "symlink-farm": "有一份目录里全是快捷方式、没有自己的文件，它不算一份真副本。",
    "shell": "其中一份正文很短，看着像转发壳 —— 它本来就不装内容，把内容并过去才是对的。",
    "fork": "两份正文各自改过，留哪份是你的取舍，工具不替你决定。",
}


def conflict_shape(ents):
    """「正文不一致」其实是好几种情况。先把不是「取舍问题」的挑出来，剩下的才该问人。

    对使用者的价值是减法：坏链、软链农场、转发壳这三类不该让他做选择，工具直接判掉；
    他只需要面对真正的「两个版本各有改动」。实测本机 16 组「正文不一致」里有 4 组属于前三类。
    """
    if any(not e.get("path_exists", True) for e in ents):
        return "broken"
    if any(not e.get("real_file_count") and e.get("link_file_count") for e in ents):
        return "symlink-farm"
    big = max((e.get("total_bytes") or 0) for e in ents)
    if big >= 1200 and any(
            (e.get("total_bytes") or 0) < 400 and big >= 3 * max(1, e.get("total_bytes") or 0)
            for e in ents):
        return "shell"
    return "fork"


def prescribe(kind, nature, liveness, ents, ignored=False):
    """给一组冲突开处方：怎么做、能不能自动做、留哪一份。

    推荐正本只从「可用副本」里挑 —— 断链、空壳、软链农场、商店/内置、已停用全部出局。
    全都不可用时宁可不给推荐（页面会说明原因），也不要把一份坏的推给人。
    """
    if ignored:
        return {"grade": "none", "action": "已确认，不再提醒",
                "why": "你在 overrides.json 里把这组标成「都留着」了。想改动时把那一条删掉再重扫。"}
    if nature == "coexist":
        return {"grade": "none", "action": "不动",
                "why": "不同来源的同名技能，硬合并会让一侧的升级链路失效。"}
    if liveness == "dormant":
        return {"grade": "none", "action": "不动",
                "why": "所有副本都处于禁用状态，属于历史残留，想清理则直接卸载。"}
    # 形态细分只服务于「正文真的不一致」这一档。半自动组的正文是逐字一致的，给它贴
    # 「正文各有改动」是错的 —— 那一档要说明的是附加文件差在哪，不是正文分叉。
    shape = conflict_shape(ents) if kind == "divergent" else None
    usable = [x for x in ents if candidate_usable(x)[0]]
    # 转发壳不推荐当正本：它本来就不装内容，把内容并过去才对。只在候选里说明，不静默剔除。
    shells = set()
    if shape == "shell":
        biggest = max((e.get("total_bytes") or 0) for e in ents)
        shells = {x["real_path"] for x in ents
                  if (x.get("total_bytes") or 0) < 400
                  and biggest >= 3 * max(1, x.get("total_bytes") or 0)}
        usable = [x for x in usable if x["real_path"] not in shells]
    mode = {"divergent": "time", "same-body-diff-files": "content"}.get(kind, "stable")
    best = (max(usable, key=lambda x: (canonical_rank(x, mode), x["link_count"]))
            if usable else None)
    note = canonical_note(best, [x for x in usable if x is not best], mode) if best else ""
    reason_why = {
        "identical": "内容逐字一致，改完不会有任何行为差异。",
        "meta-only": "正文与文件结构一致，只有 frontmatter 不同。",
        "same-body-diff-files": "正文一致但文件集不同 —— 典型的「复制过去之后各自又长了东西」。",
        "divergent": "两份正文各自改过，留哪份是你的取舍，工具不替你决定。",
    }[kind]
    table = {
        "identical": ("auto", "保留一份作正本，其余改为指向它的快捷方式"),
        "meta-only": ("auto", "保留一份作正本，其余改为快捷方式，元数据以正本为准"),
        "same-body-diff-files": ("semi", "先确认要保留哪些附加文件，再改为快捷方式"),
        "divergent": ("manual", "选一份为准，其余改为指向它的快捷方式"),
    }[kind]
    other = [x for x in ents if best and x["real_path"] != best["real_path"]]
    # 「工具可自行修复」：该被替换的每一份后面都什么都没有（断链）。这种组里没有取舍可言 ——
    # 把链指回正本谁都不损失，所以不该让人做选择题。判定只此一处，页面与执行都读它，
    # 免得两边各写一份规则、慢慢漂开。
    auto_repairable = bool(best) and bool(other) and all(
        not x.get("path_exists", True) and x.get("link_at") for x in other)
    out = {
        "grade": table[0], "action": table[1], "why": reason_why,
        "canonical": best["real_path"] if best else None,
        "canonical_agents": best["agents"] if best else [],
        "canonical_why": note,
        "auto_repairable": auto_repairable,
        "rewrite": [{"path": x["real_path"], "agents": x["agents"],
                     "link_count": x["link_count"]} for x in other],
        "needs_diff": kind == "same-body-diff-files",
        "candidates": [{"path": x["real_path"],
                        "usable": x["real_path"] not in shells and candidate_usable(x)[0],
                        "why": candidate_usable(x)[1] or (
                            "正文很短，疑似转发壳，不建议留在它这儿" if x["real_path"] in shells
                            else ""),
                        "agents": x.get("agents") or [], "type": x.get("type"),
                        "state": x.get("state"), "mtime": x.get("mtime") or 0,
                        "mtime_text": _short_time(x.get("mtime") or 0),
                        "version": x.get("version"), "version_source": x.get("version_source"),
                        "file_count": x.get("file_count"), "total_bytes": x.get("total_bytes"),
                        "root_label": x.get("root_label")}
                       for x in ents],
    }
    if shape:
        out["shape"] = shape
        out["shape_label"] = SHAPE_LABEL[shape]
        out["shape_sentence"] = SHAPE_SENTENCE[shape]
        # 「工具可判定」：这一组其实没什么可取舍的（候选只剩一份，或形态本就不是分叉）。
        out["decidable"] = bool(best) and (shape != "fork" or len(usable) == 1)
    return out


def conflict_ignores(overrides):
    """overrides.json 里被标成「都留着、别再提醒」的冲突组 → {名字: 说明}。

    冲突里有一类没有正确答案：两份都还在用（不同 agent 各喂一份），或者就看不出差别、
    决定先不动。以前没有出口，这些组就永远挂在「待处理」里，数字一直红着，久了就没人看了。
    """
    out = {}
    for name, ov in ((overrides or {}).get("by_conflict") or {}).items():
        if not isinstance(ov, dict):
            continue
        if ov.get("ignore"):
            out[name] = ov.get("note") or ""
    return out


def analyze_conflicts(entities, conflict_overrides=None):
    by_name = defaultdict(list)
    for e in entities:
        by_name[e["name"]].append(e)
    ignored = conflict_ignores(conflict_overrides)
    conflicts = []
    for name, group in by_name.items():
        if len({e["real_path"] for e in group}) < 2:
            continue
        full = {e["full_hash"] for e in group}
        body = {e["body_hash"] for e in group}
        files = {e["file_count"] for e in group}
        if len(full) == 1:
            kind = "identical"
        elif len(body) == 1 and len(files) == 1:
            kind = "meta-only"
        elif len(body) == 1:
            kind = "same-body-diff-files"
        else:
            kind = "divergent"
        ents = [{"real_path": e["real_path"], "type": e["type"],
                 "agents": e["agents"], "link_count": e["link_count"],
                 "entity_agents": e["entity_agents"],
                 "file_count": e["file_count"], "total_bytes": e["total_bytes"],
                 "body_hash": e["body_hash"], "verdict": e["verdict"],
                 "version": e.get("version"), "bundle": e.get("bundle"),
                 "plugin_key": e.get("plugin_key"),
                 "state": e.get("overall_state"), "states": e.get("states") or {},
                 "off_agents": e.get("off_agents") or [],
                 "root_label": e.get("root_label"),
                 # 判断「这份能不能当正本」「最近被动过没有」要用的三个数，
                 # 之前只传了 file_count，分不出空目录 / 只有软链的目录 / 真有内容。
                 "path_exists": e.get("path_exists", True),
                 "real_file_count": e.get("real_file_count", 0),
                 "link_file_count": e.get("link_file_count", 0),
                 "mtime": e.get("mtime") or 0,
                 "version_source": e.get("version_source"),
                 # 断链落在哪儿。有它才谈得上「把这条链指回正本」。
                 "link_at": list(e.get("link_at") or [])}
                for e in sorted(group, key=lambda x: x["real_path"])]
        vers = sorted({x["version"] for x in ents if x.get("version")})
        bundles = {x["bundle"] for x in ents if x.get("bundle")}
        nature, nature_why = classify_nature(ents)
        n_off = sum(1 for x in ents if x["state"] == "off")
        liveness = "dormant" if n_off == len(ents) else ("mixed" if n_off else "live")
        conflicts.append({
            "name": name, "kind": kind, "count": len(group), "entities": ents,
            "versions": vers,
            "bundle": next(iter(bundles)) if len(bundles) == 1 else None,
            # 只有「内容真的不同」才算版本漂移。内容逐字节一致的，版本号差异只是打包口径，
            # 不该被说成漂移（superpowers 4.0.3 vs 5.0.4 里有 5 个技能就是这种情况）。
            "version_drift": vers if (len(vers) > 1 and kind != "identical") else [],
            # 新增两个维度：同名异物 vs 真重复 / 是否真的同时在生效
            "nature": nature, "nature_why": nature_why, "liveness": liveness,
            "disabled_count": n_off,
            "ignored": name in ignored,
            "ignore_note": ignored.get(name, ""),
            "prescription": prescribe(kind, nature, liveness, ents,
                                      ignored=name in ignored),
        })
    order = {"identical": 0, "meta-only": 1, "same-body-diff-files": 2, "divergent": 3}
    # 只把「真重复且仍有副本在生效」的排到前面；同名异物与全禁用的一律沉底
    conflicts.sort(key=lambda c: (c["nature"] != "duplicate" or c["liveness"] == "dormant",
                                  order[c["kind"]], -c["count"], c["name"]))

    # 归组：同一上游包名下 ≥3 个冲突 → 汇总成一条组信息，避免刷屏
    gidx = defaultdict(list)
    for i, c in enumerate(conflicts):
        if c["bundle"]:
            gidx[c["bundle"]].append(i)
    groups = []
    for b, idx in gidx.items():
        if len(idx) < 3:
            continue
        members = [conflicts[i] for i in idx]
        vers = sorted({v for m in members for v in m["versions"]})
        groups.append({
            "bundle": b, "count": len(idx),
            "names": sorted(m["name"] for m in members),
            "versions": vers,
            "version_drift": vers if len(vers) > 1 else [],
            "kinds": sorted({m["kind"] for m in members}),
            "natures": sorted({m["nature"] for m in members}),
        })
        for i in idx:
            conflicts[i]["group"] = b
    groups.sort(key=lambda g: -g["count"])
    return conflicts, groups


# ---------------------------------------------------------------- 安装指令

def install_note(install_rules, rule_id):
    """取一条 install 期规则的说明。规则表是数据源，代码不另抄一份文案。"""
    for r in install_rules or ():
        if r.get("id") == rule_id:
            return f"[{r['id']}] {r.get('desc') or r.get('label') or ''}".strip()
    return ""


def build_install_text(entity, target_agent, agents_cfg, install_rules=()):
    hint = target_agent.get("install_hint") or "~/skills/"
    dest = hint.rstrip("/") + "/" + entity["name"]
    src = entity["real_path"]
    support = target_agent.get("supports_symlink", None)
    advisory = ""
    if support is True:
        mode = f"软链（{target_agent['label']} 已验证支持软链）"
    elif support is False:
        mode = f"复制（{target_agent['label']} 已知不支持软链）"
    else:
        mode = f"复制优先（{target_agent['label']} 软链支持未知，保守用复制）"
        advisory = install_note(install_rules, "symlink-target-unknown")

    fails = [c for c in entity["checks"] if c["level"] == "fail"]
    warns = [c for c in entity["checks"] if c["level"] == "warn"]
    if fails:
        verdict = f"FAIL — {len(fails)} 项阻塞项未清：" + "、".join(c["label"] for c in fails)
    elif warns:
        verdict = f"PASS（{len(warns)} 项提示：" + "、".join(c["label"] for c in warns) + "）"
    else:
        verdict = "PASS — 无阻塞项、无提示"

    bits = []
    if entity["deps"]["tools"]:
        bits.append("CLI: " + ", ".join(entity["deps"]["tools"]))
    if entity["deps"]["skills"]:
        bits.append("其他 skill: " + ", ".join(entity["deps"]["skills"]))
    if entity["deps"]["mcp"]:
        bits.append("需要 MCP 连接")
    deps = "；".join(bits) if bits else "无显式依赖声明"

    lines = [f"【安装 skill】{entity['name']}",
             f"唯一实体: {src}",
             f"建议落位: {dest}",
             f"方式: {mode}"]
    if advisory:
        lines.append(f"提示: {advisory}")
    lines += [f"前置校验: {verdict}",
              f"依赖: {deps}",
              "执行:"]
    if support is True:
        lines.append(f'  ln -s "{src}" "{dest}"')
        lines.append(f'  回退: cp -R "{src}" "{dest}"')
    else:
        lines.append(f'  cp -R "{src}" "{dest}"')
    if entity["link_count"]:
        lines.append(f"说明: 该实体当前已被 {entity['link_count']} 处软链引用"
                     f"（{', '.join(entity['link_agents'])}），迁移后请勿直接改动源目录内容。")
    return "\n".join(lines)


# ---------------------------------------------------------------- 启用状态

# 实测：四个 agent 四种开关机制、两种粒度，没法统一，所以按 agents.json 的声明式
# 适配逐 agent 解析。这里只做「读」，写操作在后面的「写操作层」。
PLUGIN_IN_CACHE_RE = re.compile(r"/plugins/cache/([^/]+)/([^/]+)/")

# 状态只有四种，且是可排序的「严苛度」：on < model_off < off
STATE_RANK = {"on": 0, "model_off": 1, "off": 2}
STATE_UNKNOWN = "unknown"
STATE_NA = "n/a"


def plugin_key_of(real_path):
    """从 ~/.../plugins/cache/<marketplace>/<plugin>/... 解析出 "<plugin>@<marketplace>"。

    WorkBuddy 的 workbuddy-builtin 插件同样落在 plugins/cache 下，所以这一条规则
    同时覆盖「市场安装」与「App 内置」两类。
    """
    m = PLUGIN_IN_CACHE_RE.search(real_path)
    if not m:
        return None, None
    marketplace, plugin = m.group(1), m.group(2)
    return f"{plugin}@{marketplace}", plugin


def overlay_key_of(entity):
    """WorkBuddy skillOverrides 的键：frontmatter.name 优先，没有才退回目录名。

    必须与 agent-cli 运行时用的 skill.name 一致，否则写进去的开关在运行时查不到
    （源码注释明确点名了 folder=issue_skill / name="Issue creator" 这种场景）。
    """
    return (entity.get("fm_name") or os.path.basename(entity["real_path"].rstrip("/"))).strip()


def _dig(doc, container):
    cur = doc
    for k in container or []:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur if isinstance(cur, dict) else None


def load_toggle_snapshot(agents_cfg):
    """把所有 agent 的开关文件一次性读进内存，避免逐实体重复 IO。

    返回 {agent_id: {"stores": {path_key: dict_or_None}, "spec": toggle_spec}}
    """
    snap = {}
    for agent in agents_cfg.get("agents", []):
        spec = agent.get("toggle")
        if not spec:
            continue
        paths = set()
        if spec.get("file"):
            paths.add(spec["file"])
        for key in ("plugin", "fallback"):
            sub = spec.get(key) or {}
            if sub.get("file"):
                paths.add(sub["file"])
        for r in spec.get("state_readers") or []:
            if r.get("file"):
                paths.add(r["file"])
        stores = {}
        for p in paths:
            full = expand(p)
            key = os.path.join(full, "|".join(spec.get("container") or []))
            stores[full] = load_json(full)
        snap[agent["id"]] = {"stores": stores, "spec": spec}
    return snap


def stale_toggle_source(agents_cfg, doc_path):
    """扫描产物 vs 开关文件，谁更新？

    state / check / 页面读的都是最近一次 scan 的快照 —— 改完开关不重扫，
    看到的仍是旧状态。这不是猜测，但对新用户是个陷阱，所以这里主动检测并提示。

    返回 (是否过期, 最新的那个开关文件路径)。
    """
    try:
        doc_mtime = os.path.getmtime(doc_path)
    except OSError:
        return False, None

    newest, newest_path = doc_mtime, None
    for agent in agents_cfg.get("agents", []) or []:
        spec = agent.get("toggle") or {}
        files = [spec.get("file")]
        files += [(spec.get(key) or {}).get("file") for key in ("plugin", "fallback")]
        files += [reader.get("file") for reader in (spec.get("state_readers") or [])]
        for candidate in files:
            if not candidate:
                continue
            path = expand(candidate)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime > newest:
                newest, newest_path = mtime, path
    return newest_path is not None, newest_path


def _read_state_from(store_doc, container, key_rule, ref, entity, spec):
    """从一份 JSON 快照里读出某个键的原始值，翻译成 on/model_off/off。"""
    box = _dig(store_doc, container)
    if box is None:
        return None, False
    if key_rule == "plugin_at_marketplace":
        key = ref.get("plugin_key")
        # Claude 把 ~/.claude/skills/<名字> 当作一个名为 <名字> 的 skills-dir 插件，
        # 所以市场缓存路径解析不出 plugin 时，退回目录名再试一次。
        if not key and spec.get("plugin_key_fallback") == "dirname":
            key = os.path.basename(entity["real_path"].rstrip("/"))
    elif key_rule == "fm_name_or_dirname":
        key = overlay_key_of(entity)
    else:
        key = os.path.basename(entity["real_path"].rstrip("/"))
    if not key:
        return None, False
    if key not in box:
        return "on", True            # 键不存在 = 未被关掉
    raw = box[key]
    if spec.get("value_mode") == "object_field":
        field = spec.get("value_field") or "enabled"
        if not isinstance(raw, dict):
            return STATE_NA, True
        if field not in raw:
            return "on", True
        raw = raw[field]
    for st, v in (spec.get("set") or {}).items():
        if v is not None and raw == v:
            return st, True
    return STATE_NA, True


def resolve_filemove_state(ref, agent):
    """没有原生开关的 agent：只能用文件级手段，状态来自扫描时的标记。"""
    return ("off", True) if ref.get("file_disabled") else ("on", True)

def resolve_agent_state(agent, entity, ref, snap):
    """返回 (state, known, source_str)。

    state ∈ on / model_off / off 是确定的；
    任何一种「说不清」都归到 STATE_NA（无开关记录），不再单独造一个刺眼的「未知」——
    因为对本地自建技能来说，「这个 agent 根本没有覆盖记录」本来就是正常情况。
    """
    entry = snap.get(agent["id"])
    spec = (entry or {}).get("spec")
    if not spec:
        return STATE_NA, False, "该 agent 未声明开关机制（不适用）"
    if spec.get("granularity") == "none":
        st, known = resolve_filemove_state(ref, agent)
        return st, known, "文件级（该 agent 无原生开关）"

    states = []
    sources = []
    # 1) 技能级开关
    if spec.get("file") and spec.get("container"):
        doc = entry["stores"].get(expand(spec["file"]))
        st, known = _read_state_from(doc, spec.get("container"), spec.get("key_rule"),
                                     ref, entity, spec)
        if known and st:
            states.append(st)
            sources.append(f"技能开关 {os.path.basename(spec['file'])}:{'.'.join(spec['container'])}")
    # 2) 插件级开关（技能级没命中时的兜底，也是 claude / codex 的唯一手段）
    sub = spec.get("plugin") or (spec if spec.get("granularity") == "plugin" else None)
    if sub and sub.get("file") and sub.get("container"):
        sub_spec = dict(spec)
        sub_spec.update(sub)
        doc = entry["stores"].get(expand(sub["file"]))
        st, known = _read_state_from(doc, sub.get("container"), sub.get("key_rule"),
                                     ref, entity, sub_spec)
        if known and st:
            states.append(st)
            sources.append(f"插件开关 {ref.get('plugin_key') or os.path.basename(entity['real_path'])}")
    for r in spec.get("state_readers") or []:
        doc = entry["stores"].get(expand(r["file"]))
        st, known = _read_state_from(doc, r.get("container"), r.get("key_rule"),
                                     ref, entity, spec)
        if known and st:
            states.append(st)
            sources.append(f"{os.path.basename(r['file'])}:{'.'.join(r.get('container') or [])}")
    if not states:
        return STATE_NA, False, "开关文件里没有该条目的覆盖记录（按未覆盖处理，即启用）"
    worst = max(states, key=lambda s: STATE_RANK.get(s, 9))
    return worst, True, " · ".join(dict.fromkeys(sources))


def state_label(agent, state):
    if state in (STATE_UNKNOWN, STATE_NA):
        return "无开关记录"
    t = (agent.get("toggle") or {})
    return (t.get("state_labels") or {}).get(state) or {
        "on": "启用", "model_off": "仅手动可用", "off": "已禁用"}.get(state, state)


def toggle_store_label(tg):
    """开关落点的一句话描述 —— CLI 型要给命令，不能只甩个二进制名。"""
    tg = tg or {}
    if tg.get("file"):
        return tg["file"]
    fb = tg.get("fallback") or {}
    cli = tg.get("cli") or {}
    if cli.get("bin"):
        s = f"{cli['bin']} plugin disable/enable"
        return f"{s}（兜底 {fb['file']}）" if fb.get("file") else s
    return fb.get("file") or "—"


# ------------------------------------------------- 本地产物层 / 写操作层
#
# 这一层的东西全部是「本地产物」：只对本机有意义，不该跟着 skill 目录走。
# 原因见文件头 —— 目录可能只读、升级会整目录替换、内容含本机路径与凭据原文。
# 落点优先级：--out > $SKILL_PANEL_OUT > ~/.skill-panel
STATE_ROOT = os.path.join(HOME, ".skill-panel")
OUT_HELP = "本地产物落点；缺省 $SKILL_PANEL_OUT，再缺省就是 ~/.skill-panel"
_ARTIFACT_OVERRIDE = None


def set_artifact_root(value):
    """由 main() 用 --out 的值调用。测试也用它把落点钉到临时目录。"""
    global _ARTIFACT_OVERRIDE
    _ARTIFACT_OVERRIDE = value


def artifact_root():
    override = _ARTIFACT_OVERRIDE or os.environ.get("SKILL_PANEL_OUT")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return STATE_ROOT


def artifact_json():
    """扫描快照。读它的地方和写它的地方必须是同一个函数，否则就是「写了没人读」。"""
    return os.path.join(artifact_root(), "data", "skills.json")


def artifact_html():
    return os.path.join(artifact_root(), "skill-panel.html")


# 旧版本把产物写在 skill 目录下的这两个位置。留着只为了提示一句，没有任何读写走它们。
LEGACY_ARTIFACT_RELPATHS = ("data/skills.json", "skill-panel.html")


def legacy_artifact_paths():
    return tuple(os.path.join(BASE, *rel.split("/")) for rel in LEGACY_ARTIFACT_RELPATHS)


def trash_root():
    return os.path.join(artifact_root(), "trash")


def ledger_path():
    return os.path.join(artifact_root(), "ledger.json")


def pretty_path(path):
    """打印给别人看时把 HOME 折成 ~。"""
    return path.replace(HOME, "~", 1) if path.startswith(HOME) else path


def path_key(path):
    """把同一个路径的不同写法归一到一把尺子上，用来判断「这是不是同一份」。

    实测踩到的坑：macOS 上 `/tmp` 是 `/private/tmp` 的软链，用户按终端里看到的 `/tmp/...`
    传进来，快照里存的却是 `/private/tmp/...`，同一条路径被判成「不属于这一组」。带软链的
    家目录同理。

    只解析父目录、不解析最后一段 —— 最后一段本身可能就是个快捷方式，解析它会把两份不同的
    副本（一份实体 + 一份指向它的快捷方式）认成同一份，那正好是这里最不该出的错。
    """
    return os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))


def missing_snapshot_hint():
    """没快照时的统一提示。把找过的路径写出来 —— 落点可配之后，
    「明明扫过却说没有」第一个要排查的就是两边落点不一致。"""
    return (f"还没有扫描产物（找的是 {pretty_path(artifact_json())}），"
            f"先跑：skillctl.py scan")


def load_ledger():
    return load_json(ledger_path()) or {"version": 1, "actions": []}


def save_ledger(doc):
    path = ledger_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def _toml_set_field(text, section, key, field, value):
    """在 [section."key"] 段落里写入 field = value；段落不存在则追加。

    只做定点文本改写，不重排整份 TOML，避免破坏用户的手写格式与注释。
    """
    lit = "true" if value is True else ("false" if value is False else json.dumps(value))
    # 段落头匹配 [section.key] / [section."key"] / [section. 'key' ]
    head = re.compile(r'^\s*\[' + re.escape(section) + r'\.\s*["\']?'
                      + re.escape(key) + r'["\']?\s*\]\s*$', re.M)
    m = head.search(text)
    if not m:
        return text.rstrip("\n") + f'\n\n[{section}."{key}"]\n{field} = {lit}\n'
    start = m.end()
    nxt = re.compile(r'^\s*\[', re.M).search(text, start)
    end = nxt.start() if nxt else len(text)
    block = text[start:end]
    fm = re.compile(r'^(\s*)' + re.escape(field) + r'\s*=.*$', re.M)
    if fm.search(block):
        nb = fm.sub(lambda mm: f"{mm.group(1)}{field} = {lit}", block, count=1)
    else:
        nb = block.rstrip("\n") + f"\n{field} = {lit}\n"
    return text[:start] + nb + text[end:]


def build_ops(agents_cfg, entity, agent_id, action):
    """把一次操作翻译成一串可复核、可干跑、可回滚的原子动作。

    动作种类：
      json_set — 改 JSON 里的某个键（value 为 None 表示删除该键）
      toml_set — 改 TOML 段落里的某个字段
      cli      — 调 agent 自带命令
      move     — 移动目录/文件（卸载与文件级禁用用）
    """
    agent = next((a for a in agents_cfg.get("agents", []) if a["id"] == agent_id), None)
    if not agent:
        raise ValueError(f"适配表里没有 agent「{agent_id}」")
    ref = next((r for r in entity["refs"] if r["agent"] == agent_id), None)
    if not ref:
        raise ValueError(f"{agent['label']} 并未持有「{entity['name']}」，没有可操作的对象")
    spec = agent.get("toggle") or {}
    target_state = "off" if action == "disable" else "on"
    ops = []

    def _json_op(s):
        key = ref.get("plugin_key") if s.get("key_rule") == "plugin_at_marketplace" \
            else (overlay_key_of(entity) if s.get("key_rule") == "fm_name_or_dirname"
                  else os.path.basename(entity["real_path"].rstrip("/")))
        if key is None and s.get("plugin_key_fallback") == "dirname":
            key = os.path.basename(entity["real_path"].rstrip("/"))
        if key is None:
            raise ValueError(f"无法为「{entity['name']}」生成开关键（{agent['label']} 的开关是插件级的，"
                             f"但这条记录不在任何插件目录下）")
        val = (s.get("set") or {}).get(target_state)
        base = {"kind": "json_set", "file": s["file"],
                "container": list(s.get("container") or []), "key": key, "value": val}
        if s.get("value_mode") == "object_field":
            base["value_field"] = s.get("value_field") or "enabled"
            base["desc"] = (f"{os.path.basename(s['file'])} → "
                            f"{'.'.join(s.get('container') or [])}[\"{key}\"]"
                            f".{base['value_field']} = {val}")
        else:
            base["desc"] = (f"{os.path.basename(s['file'])} → "
                            f"{'.'.join(s.get('container') or [])}[\"{key}\"]"
                            + (" 删除该键（等于恢复启用）" if val is None else f" = {val}"))
        return base

    # 没有原生开关的 agent：退到文件级
    if spec.get("granularity") == "none":
        base = entity["real_path"].rstrip("/")
        dest = os.path.join(os.path.dirname(base), ".disabled", os.path.basename(base))
        if action == "disable":
            ops.append({"kind": "move", "src": base, "dst": dest,
                        "desc": f"移动到 {dest.replace(HOME, '~')}（点开头目录各 agent 扫描时忽略）"})
        else:
            ops.append({"kind": "move", "src": dest, "dst": base,
                        "desc": f"移回 {base.replace(HOME, '~')}"})
        return ops, agent

    writer = spec.get("writer")
    if writer == "cli":
        cli = spec.get("cli") or {}
        plugin = (ref.get("plugin_key") or "").split("@", 1)[0] \
            or os.path.basename(entity["real_path"].rstrip("/"))
        verb = "disable" if action == "disable" else "enable"
        if cli.get("bin"):
            op = {"kind": "cli",
                  "argv": [cli["bin"]] + [a.replace("{plugin}", plugin)
                                          for a in (cli.get(verb) or [])],
                  "cwd": HOME,
                  "desc": f"{cli['bin']} plugin {verb} {plugin}"
                          f"（走 {agent['label']} 自带命令，最安全）"}
            fb = spec.get("fallback")
            if fb:
                try:
                    op["fallback"] = [_json_op(fb)]
                    op["desc"] += f"；命令不可用时回退到改 {os.path.basename(fb['file'])}"
                except ValueError:
                    pass
            ops.append(op)
            return ops, agent
        if spec.get("fallback"):
            ops.append(_json_op(spec["fallback"]))
            return ops, agent

    if writer == "toml_section":
        val = (spec.get("set") or {}).get(target_state)
        pk = ref.get("plugin_key")
        if not pk:
            raise ValueError(f"「{entity['name']}」不在 {agent['label']} 的插件目录下，"
                             f"而它的开关是插件级的，没有可写的对象")
        ops.append({"kind": "toml_set", "file": spec["file"],
                    "section": spec.get("section") or "plugins", "key": pk,
                    "field": spec.get("field") or "enabled", "value": val,
                    "desc": f"{os.path.basename(spec['file'])} → "
                            f"[{spec.get('section') or 'plugins'}.\"{pk}\"] "
                            f"{spec.get('field') or 'enabled'} = {val}"})
        return ops, agent

    ops.append(_json_op(spec))
    return ops, agent


def apply_ops(ops, dry_run=True):
    """执行动作。dry_run=True 时只回报将要发生什么，不碰磁盘。"""
    log = []
    for op in ops:
        k = op["kind"]
        if k == "json_set":
            fp = expand(op["file"])
            before_doc = load_json(fp)
            after_doc = json.loads(json.dumps(before_doc)) if before_doc is not None else {}
            box = after_doc
            for c in op["container"]:
                box = box.setdefault(c, {})
            old = box.get(op["key"], "<不存在>")
            if op.get("value_field"):
                cur = box.get(op["key"]) if isinstance(box.get(op["key"]), dict) else {}
                new = dict(cur)
                new[op["value_field"]] = op["value"]
                box[op["key"]] = new
                shown = f"{op.get('value_field')}: {cur.get(op.get('value_field'), '<不存在>')} → {op['value']}"
            elif op["value"] is None:
                box.pop(op["key"], None)
                shown = f"{old} → 删除"
            else:
                box[op["key"]] = op["value"]
                shown = f"{old} → {op['value']}"
            if not dry_run:
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                if os.path.isfile(fp):
                    shutil.copy2(fp, fp + ".skillctl.bak")
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(after_doc, f, ensure_ascii=False, indent=2)
            where = ".".join(op["container"] + [op["key"]])
            log.append(f"[配置] {op['file'].replace(HOME, '~')}  {where}  {shown}")
        elif k == "toml_set":
            fp = expand(op["file"])
            text = read_text(fp)
            new_text = _toml_set_field(text, op["section"], op["key"], op["field"], op["value"])
            changed = new_text != text
            if not dry_run and changed:
                if os.path.isfile(fp):
                    shutil.copy2(fp, fp + ".skillctl.bak")
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(new_text)
            log.append(f"[toml] {op['file'].replace(HOME, '~')}  {op['desc']}  ({'已改' if changed else '无变化'})")
        elif k == "cli":
            argv = list(op["argv"])
            argv[0] = shutil.which(argv[0]) or argv[0]
            if dry_run:
                log.append(f"[cli ] 将执行：{' '.join(argv)}")
            else:
                ok, detail = False, ""
                try:
                    r = subprocess.run(argv, cwd=op.get("cwd") or HOME,
                                       capture_output=True, text=True, timeout=90)
                    ok = r.returncode == 0
                    detail = (r.stdout or r.stderr or "").strip()[:400]
                except FileNotFoundError:
                    detail = f"命令不存在：{argv[0]}"
                except Exception as exc:                       # noqa: BLE001
                    detail = f"{type(exc).__name__}: {exc}"
                if ok:
                    log.append(f"[cli ] {' '.join(argv)}  成功"
                               + (f"\n{detail}" if detail else ""))
                elif op.get("fallback"):
                    log.append(f"[cli ] {' '.join(argv)}  失败：{detail}")
                    log.append("[cli ] 回退到直接改配置文件：")
                    log.extend(apply_ops(op["fallback"], dry_run=False))
                else:
                    raise RuntimeError(f"命令失败（{' '.join(argv)}）：{detail}")
        elif k == "move":
            src, dst = op["src"], op["dst"]
            if dry_run:
                log.append(f"[move] {src.replace(HOME, '~')}\n       → {dst.replace(HOME, '~')}")
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    raise RuntimeError(f"目标已存在，拒绝覆盖：{dst}")
                shutil.move(src, dst)
                log.append(f"[move] 完成 {src.replace(HOME, '~')} → {dst.replace(HOME, '~')}")
        elif k == "symlink":
            # lexists 而不是 exists —— 断链的软链同样占着这个名字，也要拦。
            dst, target = op["dst"], op["target"]
            if dry_run:
                log.append(f"[link] {dst.replace(HOME, '~')} → {target.replace(HOME, '~')}")
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.lexists(dst):
                    raise RuntimeError(f"目标已存在，拒绝覆盖：{dst}")
                os.symlink(target, dst)
                log.append(f"[link] 完成 {dst.replace(HOME, '~')} → {target.replace(HOME, '~')}")
        elif k == "unlink":
            # 只删快捷方式本身，而且必须真的是快捷方式 —— 撤销的时候宁可不做，也不能删错东西。
            path = op["path"]
            if not os.path.islink(path):
                raise RuntimeError(f"这里不是快捷方式，拒绝删除：{path}")
            if dry_run:
                log.append(f"[unln] {path.replace(HOME, '~')}（删掉这里的快捷方式）")
            else:
                os.unlink(path)
                log.append(f"[unln] 完成 {path.replace(HOME, '~')}")
    return log


def trash_path_for(entity, agent_id):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", entity["name"])[:60]
    return os.path.join(trash_root(), f"{ts}-{agent_id}", safe)


def plan_uninstall(agents_cfg, entity, agent_id):
    """卸载 = 把该 agent 下的这条记录移进回收站。

    三种情况分开处理：
      · 只是快捷方式 → 删链接（零损失，实体在别处）
      · 实体持有且没有别的 agent 引用 → 整个目录移进回收站
      · 实体持有但被别的 agent 引用 → 拦下，除非显式 force
    """
    ref = next((r for r in entity["refs"] if r["agent"] == agent_id), None)
    if not ref:
        raise ValueError(f"{agent_id} 并未持有「{entity['name']}」")
    ops, warns = [], []
    if ref["is_link"]:
        ops.append({"kind": "move", "src": ref["path"], "dst": trash_path_for(entity, agent_id),
                    "desc": f"删除快捷方式（本体在 {entity['real_path'].replace(HOME, '~')}，不受影响）"})
        return ops, warns
    others = [r for r in entity["refs"] if r["agent"] != agent_id and r["is_link"]]
    if others and not force_ok(entity, agent_id):
        names = "、".join(sorted({r["agent"] for r in others}))
        warns.append(f"实体本体在这里，但被 {names} 以快捷方式引用 —— 直接移走会让它们的引用失效。"
                     f"先改掉那些引用，或勾选「同时清理引用」再执行。")
    ops.append({"kind": "move", "src": entity["real_path"],
                "dst": trash_path_for(entity, agent_id),
                "desc": f"移入回收站 {pretty_path(trash_root())}/（不删除，可 restore 还原）"})
    for r in others:
        ops.append({"kind": "move", "src": r["path"], "dst": trash_path_for(entity, r["agent"]),
                    "desc": f"同时移走 {r['agent']} 的失效引用"})
    return ops, warns


_FORCE_FLAG = {"value": False}


def force_ok(entity, agent_id):
    return _FORCE_FLAG["value"]


def uninstall_entity(doc, agents_cfg, name, agent_id, force=False, dry_run=True):
    entity = find_entity(doc, name, agent_id)
    if not entity:
        raise ValueError(f"没找到 skill「{name}」")
    builtin = [r for r in entity["refs"] if not r["is_link"]] or entity["refs"]
    if entity["type"] == "builtin":
        raise ValueError(f"「{name}」是 App 内置技能（{entity['type_evidence']}）—— "
                         f"删掉它会破坏 App 功能，且下次升级/重装还会回来。已拒绝。")
    _FORCE_FLAG["value"] = force
    ops, warns = plan_uninstall(agents_cfg, entity, agent_id)
    if warns and not force:
        raise RuntimeError("；".join(warns))
    log = apply_ops(ops, dry_run=dry_run)
    if not dry_run:
        led = load_ledger()
        led["actions"].append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "action": "uninstall", "name": entity["name"], "agent": agent_id,
            "ops": [{"kind": o["kind"], "src": o.get("src"), "dst": o.get("dst")} for o in ops],
        })
        save_ledger(led)
    return log, warns, ops


def resolve_conflict(doc, agents_cfg, names=None, allow_semi=False, dry_run=True,
                     canonical_map=None):
    """把重复冲突真正落盘：留一份作正本，其余换成指向它的快捷方式。

    跟 `plan` 的分工：plan 只出清单和脚本给人复核，一个字节都不动；这里直接改，
    但同样干跑优先 —— 页面按钮先取一份差量，用户点头之后才落盘。

    三档的进入条件不同：
      · auto / semi —— 脚本可判定，semi 要显式 allow_semi；
      · manual（正文已分叉）—— 只在 canonical_map 里**明确指定了留哪一份**时才处理。
        「留哪份」是你的取舍，工具不替你挑；但你挑了，剩下的搬移换链就不该让你手工做。

    canonical_map 的路径必须落在**这次快照里该组真实存在的副本**上 —— 请求里的路径不能直接信，
    否则一个畸形请求就能把任意目录移进回收站、再在原地建一个指向任意位置的快捷方式。
    """
    canon_map = canonical_map or {}
    grades = ("auto", "semi") if allow_semi else ("auto",)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    groups, ops, skipped, warnings = [], [], [], []
    for c in doc.get("conflicts") or []:
        if c.get("nature") != "duplicate" or c.get("liveness") == "dormant":
            continue
        if names and c["name"] not in names:
            continue
        p = c.get("prescription") or {}
        grade = p.get("grade")
        chosen = canon_map.get(c["name"])
        if grade == "manual" and not chosen and not p.get("auto_repairable"):
            # 正文分叉那档默认必须由人指定留哪一份。唯一的例外是「该被替换的那些副本后面
            # 什么都没有」—— 也就是断链：它只是一条指向空气的快捷方式，把它指回正本不涉及
            # 任何取舍，判定见 prescribe 里的 auto_repairable。除此之外一律交给人，包括软链
            # 农场（那些链可能各自指向不同地方，换掉会丢映射）和转发壳（它有正文，换掉就是丢正文）。
            skipped.append({"name": c["name"],
                            "why": "正文已分叉，要你在页面上指定留哪一份才动手"})
            continue
        if grade not in grades and grade != "manual":
            if grade == "semi":
                why = "半自动组（正文一致但文件集不同）要显式加 --semi 才处理"
            else:
                why = f"级别 {grade} 不在本次范围"
            skipped.append({"name": c["name"], "why": why})
            continue
        if chosen:
            # 只认这次快照里的副本。传进来的路径再合理也不信 —— 但两种等价写法要能对上，
            # 否则用户按终端里的路径传进来会被自己的机器判成非法。
            key = path_key(chosen)
            match = next((e for e in (c.get("entities") or [])
                          if path_key(e["real_path"]) == key), None)
            if not match:
                skipped.append({"name": c["name"],
                                "why": f"指定的那份不属于这一组，已拒绝：{pretty_path(chosen)}"})
                continue
            blocked = canonical_blocked(match)
            if blocked:
                skipped.append({"name": c["name"],
                                "why": f"指定的那份不能当正本（{blocked}）：{pretty_path(chosen)}"})
                continue
            canon = match["real_path"]
        else:
            canon = p.get("canonical")
        if not canon or not os.path.isdir(canon) or os.path.islink(canon):
            warnings.append(f"{c['name']}：候选正本 {pretty_path(canon or '(空)')} 不可用"
                            f"（不存在／不是目录／本身还是个快捷方式），跳过。")
            continue
        targets = []
        # 要换掉哪几份必须**按这次实际选定的正本重算**，不能照抄扫描期的 rewrite ——
        # 那个列表是针对「推荐正本」算的，用户一旦改选另一份，它恰好把用户选中的那份列成
        # 待替换对象，结果就是什么都不做（实测：--canonical 指定后静默无输出）。
        for e in sorted(c.get("entities") or [], key=lambda x: x["real_path"]):
            src = e["real_path"]
            if src == canon:
                continue
            if not e.get("path_exists", True):
                # 断链。src 是「它指向的那个不存在的目标」，链真正待在哪儿要看 link_at。
                # 把链指回正本是**修复**而不是取舍 —— 后面什么都没有，没有东西要进回收站，
                # 这也是唯一能让这一份重新可用的动作。
                stamped = list(e.get("link_at") or [])
                if stamped:
                    for at in stamped:
                        targets.append((at, (e.get("agents") or ["?"])[0], None, True))
                else:
                    warnings.append(f"{c['name']}：{pretty_path(src)} 不存在，跳过。")
                continue
            if os.path.islink(src):
                skipped.append({"name": c["name"],
                                "why": f"{pretty_path(src)} 已经是能用的快捷方式"})
                continue
            if not os.path.lexists(src):
                # 再验一次实时状态：快照可能已经过期（扫完之后目录被手工删掉／挪走了）。
                warnings.append(f"{c['name']}：{pretty_path(src)} 不存在，跳过。")
                continue
            if e.get("type") in ("market", "builtin"):
                # 渠道管的副本不动：换成快捷方式后，商店/内置升级会把整个目录换回来，
                # 去重白做；反过来让它当正本，别的副本就会指向随时会被清掉的缓存目录。
                warnings.append(f"{c['name']}：{pretty_path(src)} 来自技能商店或 App 内置，"
                                f"不换成快捷方式（升级会覆盖），保持原样。")
                continue
            agent_id = (e.get("agents") or ["?"])[0]
            safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", c["name"])[:60]
            dst = os.path.join(trash_root(), f"conflict-{ts}-{agent_id}", safe)
            targets.append((src, agent_id, dst, False))
        if not targets:
            continue
        for src, agent_id, dst, relink_only in targets:
            if relink_only:
                ops.append({"kind": "unlink", "path": src,
                            "desc": f"先撤掉这条断掉的快捷方式：{pretty_path(src)}"})
            else:
                ops.append({"kind": "move", "src": src, "dst": dst,
                            "desc": f"移入回收站（不删除）：{pretty_path(dst)}"})
            ops.append({"kind": "symlink", "dst": src, "target": canon,
                        "desc": f"原位建快捷方式指向正本 {pretty_path(canon)}"})
        rewritten = [(s, a, d) for s, a, d, relink in targets if not relink]
        relinked = [s for s, _, _, relink in targets if relink]
        groups.append({"name": c["name"], "grade": grade, "canonical": canon,
                       "human_picked": bool(chosen),
                       "from": [{"path": s, "agent": a, "trash": d} for s, a, d in rewritten],
                       "relinked": relinked,
                       "trash": os.path.join(trash_root(), f"conflict-{ts}")})
    if not ops:
        return [], [], groups, skipped, warnings
    log = apply_ops(ops, dry_run=dry_run)
    if not dry_run:
        led = load_ledger()
        led["actions"].append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "action": "resolve-conflict",
            # 每份副本的回收站落点都要记 —— 撤销要照着它把目录搬回原位，
            # 从 groups[].trash 反推不出来（那个是批次目录，实际落点还带 agent 后缀）。
            "groups": [{"name": g["name"], "canonical": g["canonical"],
                        "from": [{"path": f["path"], "agent": f["agent"],
                                  "trash": f["trash"]} for f in g["from"]],
                        "relinked": list(g.get("relinked") or [])}
                       for g in groups],
        })
        save_ledger(led)
        log.append(f"已记入 {pretty_path(ledger_path())}")
    return log, ops, groups, skipped, warnings


def last_undoable():
    """上一次「一键去重」的台账摘要，给页面上的撤销按钮用。

    返回 None 表示没什么可撤销的 —— 页面据此决定按钮显示与否，别让它点了才发现没事可做。
    """
    for a in reversed(load_ledger().get("actions", [])):
        if a.get("action") != "resolve-conflict" or a.get("undone"):
            continue
        groups = a.get("groups") or []
        return {"at": a.get("at"),
                "groups": [{"name": g.get("name"), "canonical": g.get("canonical"),
                            "count": len(g.get("from") or [])} for g in groups],
                "files": sum(len(g.get("from") or []) for g in groups)}
    return None


def set_conflict_ignore(name, note="", ignore=True, dry_run=True):
    """把一组冲突标成「都先留着，别再提醒」，或取消这个标记。

    为什么需要这个出口：有些组根本没有「正确答案」—— 两份都还在正常用，或者你权衡之后
    就是决定先不动。以前没有出口，这些组会永远挂在「待处理」里，面板的数字一直红着，
    久之就没人看了。写进 overrides.json 的 by_conflict，删掉那一条再重扫即可撤销。
    """
    path = os.path.join(BASE, "overrides.json")
    # 不写默认说明：面板上那句解释已经够用，再塞一句自动生成的「注释」只会在界面上
    # 变成一层套一层的括号噪音。note 只在用户真写了的时候才存。
    entry = {"ignore": True}
    if note:
        entry["note"] = note
    value = entry if ignore else None
    op = {"kind": "json_set", "file": path, "container": ["by_conflict"],
          "key": name, "value": value,
          "desc": f"by_conflict[\"{name}\"] → {'标记为都先留着' if ignore else '删掉标记'}"}
    log = apply_ops([op], dry_run=dry_run)
    return log, [op]


def undo_resolve(doc, at=None, dry_run=True):
    """把一次「一键去重」按台账退回去：删掉原位的快捷方式、把回收站里的目录搬回原位。

    几处刻意的保守：
      · 只在回收站里那份确实还在时才动原位的快捷方式 —— 顺序反了就会把目录弄丢；
      · 原位如果不是「指向该正本的快捷方式」，就不碰（可能是你自己后来改的）；
      · 回收站缺失 / 原位被换成别的东西，一律跳过并告警，不猜、不强行重建。
    """
    led = load_ledger()
    acts = [a for a in led.get("actions", [])
            if a.get("action") == "resolve-conflict" and not a.get("undone")]
    if at:
        acts = [a for a in acts if (a.get("at") or "").startswith(at)]
    if not acts:
        return [], [], {"error": "台账里没有可撤销的「一键去重」记录",
                        "hint": f"台账：{pretty_path(ledger_path())}"}, [], []
    act = acts[-1]
    ops, groups, skipped, warnings = [], [], [], []
    for g in act.get("groups") or []:
        restored = []
        for f in g.get("from") or []:
            src, trash = f.get("path"), f.get("trash")
            if not src or not trash:
                warnings.append(f"{g.get('name')}：台账里这一条缺落点，跳过。")
                continue
            if not os.path.lexists(trash):
                warnings.append(f"{g.get('name')}：回收站里已经没有 "
                                f"{pretty_path(trash)} 了，跳过 —— 不删快捷方式，免得两头都没有。")
                continue
            if os.path.islink(src):
                target = os.readlink(src)
                if g.get("canonical") and os.path.realpath(target) != os.path.realpath(
                        g["canonical"]):
                    warnings.append(f"{g.get('name')}：{pretty_path(src)} 现在指向 "
                                    f"{pretty_path(target)}，不是这次操作留下的，跳过。")
                    continue
                ops.append({"kind": "unlink", "path": src})
            elif os.path.lexists(src):
                warnings.append(f"{g.get('name')}：{pretty_path(src)} 现在不是快捷方式"
                                f"（被换成别的东西了），跳过。")
                continue
            ops.append({"kind": "move", "src": trash, "dst": src})
            restored.append({"path": src, "trash": trash})
        if restored:
            groups.append({"name": g.get("name"), "canonical": g.get("canonical"),
                           "restored": restored})
        # 断链修复没有可还原的源 —— 那个位置上本来就是一条指向空气的快捷方式。
        # 假装能还原只会让人以为「撤了」，其实什么都没变。
        for src in g.get("relinked") or []:
            warnings.append(f"{g.get('name')}：{pretty_path(src)} 是断链修复，不还原"
                            f"（这里本来就什么都没有，撤掉只会再留一条断的）。")
    if not ops:
        # 没得还原也是正常结果（比如连点两次撤销），不算错误 —— 交给调用方按空列表处理。
        return [], [], {"groups": [], "at": act.get("at")}, skipped, warnings
    log = apply_ops(ops, dry_run=dry_run)
    if not dry_run:
        act["undone"] = datetime.now().isoformat(timespec="seconds")
        led["actions"].append({
            "at": act["undone"], "action": "undo-resolve",
            "groups": [{"name": g["name"], "restored": [r["path"] for r in g["restored"]]}
                       for g in groups],
        })
        save_ledger(led)
        # 批次目录空了就顺手收掉，别在回收站里留一堆空壳。
        for g in groups:
            for r in g["restored"]:
                parent = os.path.dirname(r["trash"])
                try:
                    os.rmdir(parent)
                except OSError:
                    pass
        log.append(f"已记入 {pretty_path(ledger_path())}")
    return log, ops, {"groups": groups, "at": act.get("at")}, skipped, warnings


def do_set_state(doc, agents_cfg, name, agent_id, action, dry_run=True, state="off"):
    entity = find_entity(doc, name, agent_id)
    if not entity:
        raise ValueError(f"没找到 skill「{name}」")
    agent = next((a for a in agents_cfg.get("agents", []) if a["id"] == agent_id), None)
    if not agent:
        raise ValueError(f"适配表里没有 agent「{agent_id}」")
    spec = agent.get("toggle")
    if not spec:
        raise ValueError(f"{agent['label']} 未声明开关机制，无法操作")
    ops, agent = build_ops(agents_cfg, entity, agent_id, action)
    # 插件级开关会连带同插件的其他技能。插件名取不到时（例如 Claude 的 skills-dir
    # 插件，每个目录自成一个插件）就不提示 —— 否则会把一堆 plugin_key 为空的记录
    # 误算成同一个插件。
    if spec.get("granularity") == "plugin" and ops:
        mine = next((r for r in entity["refs"] if r["agent"] == agent_id), None)
        pk = (mine or {}).get("plugin_key")
        if pk:
            sib = sorted({e["name"] for e in _ALL_ENTITIES
                          if e["name"] != entity["name"]
                          and any(r["agent"] == agent_id and r.get("plugin_key") == pk
                                  for r in e["refs"])})
            if sib:
                tail = "…" if len(sib) > 6 else ""
                ops[0]["blast"] = (f"{pk} 是插件级开关 —— 同插件下还有 {len(sib)} 个技能会一起"
                                   f"被{'禁用' if action == 'disable' else '启用'}："
                                   f"{'、'.join(sib[:6])}{tail}")
    log = apply_ops(ops, dry_run=dry_run)
    if not dry_run:
        led = load_ledger()
        led["actions"].append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "action": action, "name": entity["name"], "agent": agent_id, "ops": ops,
        })
        save_ledger(led)
    return log, ops


# 当前扫描的实体表，供「同插件波及面」计算用（进程内一次性赋值）
_ALL_ENTITIES = []


# ---------------------------------------------------------------- 主流程

def do_scan(args):
    agents_cfg = load_json(os.path.join(BASE, "agents.json")) or {"agents": []}
    rules_cfg = load_json(os.path.join(BASE, "rules.json")) or {"rules": []}
    overrides = load_json(os.path.join(BASE, "overrides.json")) or {}
    validate_agents_config(agents_cfg)
    validate_rules_config(rules_cfg)

    manifest_index = load_install_manifests(agents_cfg.get("install_manifests", []))
    builtin_lib_index = build_builtin_library_index(agents_cfg)
    toggle_snap = load_toggle_snapshot(agents_cfg)
    entries, skipped = iter_entries(agents_cfg, manifest_index)
    entities, install_rules = build_entities(entries, agents_cfg, rules_cfg, overrides,
                                             manifest_index, builtin_lib_index, toggle_snap)
    _ALL_ENTITIES[:] = entities
    conflicts, conflict_groups = analyze_conflicts(entities, overrides)

    broken_links = [{"agent": e["agent"], "path": e["path"], "link_raw": e["link_raw"]}
                    for e in entries if e["is_link"] and not e["exists"]]

    agent_stats = []
    for agent in agents_cfg.get("agents", []):
        rows = [e for e in entries if e["agent"] == agent["id"]]
        tg = agent.get("toggle") or {}
        agent_stats.append({
            "id": agent["id"], "label": agent["label"],
            "supports_symlink": agent.get("supports_symlink"),
            "install_hint": agent.get("install_hint"),
            "note": agent.get("note", ""),
            "prefer_as_target": bool(agent.get("prefer_as_target", False)),
            "symlink_evidence": agent.get("symlink_evidence", ""),
            "entries": len(rows),
            "links": sum(1 for r in rows if r["is_link"]),
            "owned_entities": len({r["real_path"] for r in rows if not r["is_link"]}),
            "by_kind": dict(sorted(
                __import__("collections").Counter(r["root_kind"] for r in rows).items())),
            # 开关机制：粒度 + 落点 + 是否有实证
            "toggle_granularity": tg.get("granularity") or "none",
            "toggle_store": toggle_store_label(tg),
            "toggle_evidence": tg.get("evidence", ""),
            "toggle_verified": bool(tg.get("file_level", {}).get("verified")) or bool(tg.get("evidence")),
            "toggle_plugin_store": (tg.get("plugin") or {}).get("file"),
        })

    def _count_state(pred):
        return sum(1 for e in entities if pred(e))

    stats = {
        "entries": len(entries), "entities": len(entities),
        "links": sum(1 for e in entries if e["is_link"]),
        "shared_entities": sum(1 for e in entities if len(e["agents"]) > 1),
        "conflicts": len(conflicts),
        "conflict_groups": len(conflict_groups),
        "version_drift_conflicts": sum(1 for c in conflicts if c.get("version_drift")),
        "conflict_divergent": sum(1 for c in conflicts if c["kind"] == "divergent"),
        "fail_entities": _count_state(lambda e: e["verdict"] == "fail"),
        "warn_entities": _count_state(lambda e: e["verdict"] == "warn"),
        "pass_entities": _count_state(lambda e: e["verdict"] == "pass"),
        "broken_links": len(broken_links),
        "builtin": _count_state(lambda e: e["type"] == "builtin"),
        "market": _count_state(lambda e: e["type"] == "market"),
        "local": _count_state(lambda e: e["type"] == "local"),
        "auto_created": _count_state(lambda e: e["auto_created"]),
        "total_bytes": sum(e["total_bytes"] for e in entities),
        # ---- 启用状态 ----
        "fully_off": _count_state(lambda e: e["overall_state"] == "off"),
        "partially_off": _count_state(lambda e: e["overall_state"] == "partial_off"),
        "model_off": _count_state(lambda e: e["overall_state"] in ("model_off", "partial_model_off")),
        "state_known": _count_state(lambda e: not e["unknown_state_agents"]),
        # ---- 冲突分诊 ----
        "conflict_coexist": sum(1 for c in conflicts if c["nature"] == "coexist"),
        "conflict_duplicate": sum(1 for c in conflicts if c["nature"] == "duplicate"),
        "conflict_live": sum(1 for c in conflicts if c["liveness"] == "live"),
        "conflict_mixed": sum(1 for c in conflicts if c["liveness"] == "mixed"),
        "conflict_dormant": sum(1 for c in conflicts if c["liveness"] == "dormant"),
        # 已停用的同名异物：不需要处理，只是让你知道它们已经停在那儿了
        "coexist_dormant": sum(1 for c in conflicts
                               if c["nature"] == "coexist" and c["liveness"] != "live"),
        "todo_auto": sum(1 for c in conflicts if c["prescription"]["grade"] == "auto"
                         and c["nature"] == "duplicate" and c["liveness"] != "dormant"),
        "todo_semi": sum(1 for c in conflicts if c["prescription"]["grade"] == "semi"
                         and c["nature"] == "duplicate" and c["liveness"] != "dormant"),
        "todo_manual": sum(1 for c in conflicts if c["prescription"]["grade"] == "manual"
                           and c["nature"] == "duplicate" and c["liveness"] != "dormant"),
        # 标了「都留着、别再提醒」的组不进待处理 —— 出口有没有用，全看这几个数降没降。
        "ignored_conflicts": sum(1 for c in conflicts if c.get("ignored")),
        # 「正文不一致」再按形态拆开：坏链 / 软链农场 / 转发壳这三类不该让人做选择。
        "divergent_by_shape": dict(sorted(
            __import__("collections").Counter(
                c["prescription"].get("shape") for c in conflicts
                if c["kind"] == "divergent"
                and c["nature"] == "duplicate" and c["liveness"] != "dormant"
                and not c.get("ignored")).items(),
            key=lambda kv: (kv[0] is None, kv[0]))),
    }

    rule_hits = defaultdict(int)
    for e in entities:
        for c in e["checks"]:
            rule_hits[c["id"]] += 1
    rule_meta = {r["id"]: {"label": r["label"], "level": r["level"],
                           "kind": r.get("kind"), "desc": r.get("desc", ""),
                           "enabled": r.get("enabled", True)}
                 for r in rules_cfg.get("rules", [])}

    tz = timezone(timedelta(hours=8))
    doc = {
        "generated_at": datetime.now(tz).isoformat(timespec="seconds"),
        "host": CURRENT_USER, "schema_version": 1,
        "tool_dir": ENTRY_DIR, "python_bin": sys.executable,
        "stats": stats, "agent_stats": agent_stats,
        "rule_meta": rule_meta,
        "rule_hits": dict(sorted(rule_hits.items(), key=lambda x: -x[1])),
        "conflicts": conflicts, "broken_links": broken_links,
        "conflict_groups": conflict_groups,
        "builtin_libraries": [
            {"path": l.get("path"), "for_agent": l.get("for_agent"),
             "count": len((builtin_lib_index.get(l.get("for_agent")) or {})),
             "reason": l.get("reason", "")}
            for l in agents_cfg.get("builtin_libraries", [])
        ],
        "skipped": skipped,
        "entities": sorted(entities, key=lambda e: e["name"].lower()),
        "install_rule_ids": [r["id"] for r in install_rules],
        "excluded": agents_cfg.get("excluded", []),
        "paths": {"trash": trash_root(), "ledger": ledger_path(),
                  "artifacts": artifact_root(),
                  "overrides": os.path.join(BASE, "overrides.json")},
        "ledger": (load_ledger().get("actions") or [])[-50:],
        # 页面上的撤销按钮靠它决定显示与否：没有可撤销的东西就别摆一个点了没反应的按钮。
        "undo": last_undoable(),
    }

    out_dir = os.path.dirname(artifact_json())
    os.makedirs(out_dir, exist_ok=True)
    json_path = artifact_json()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    print(f"扫描完成  {doc['generated_at']}")
    print(f"  注册记录 {stats['entries']}  快捷方式 {stats['links']}  →  真实副本 {stats['entities']}")
    print(f"  真实副本里：已禁用 {stats['fully_off']}  部分禁用 {stats['partially_off']}"
          f"  仅手动可用 {stats['model_off']}  无开关记录 {stats['entities'] - stats['state_known']}")
    print(f"  共享副本 {stats['shared_entities']}   同名冲突 {stats['conflicts']}"
          f"（真重复 {stats['conflict_duplicate']} / 同名异物 {stats['conflict_coexist']}）")
    print(f"  冲突分诊  两边都启用 {stats['conflict_live']}  一方已禁用 {stats['conflict_mixed']}"
          f"  全部已禁用 {stats['conflict_dormant']}")
    print(f"  待处理处方  可自动 {stats['todo_auto']}  半自动 {stats['todo_semi']}"
          f"  需人工 {stats['todo_manual']}")
    print(f"  类型  内置 {stats['builtin']} / 市场安装 {stats['market']} / 本地自建 {stats['local']}")
    print(f"  校验  阻塞 {stats['fail_entities']}  提示 {stats['warn_entities']}"
          f"  通过 {stats['pass_entities']}")
    print(f"  断链 {stats['broken_links']}")
    print(f"  → {pretty_path(json_path)}")
    if not args.no_html:
        tpl = os.path.join(BASE, "assets", "dashboard_template.html")
        if os.path.isfile(tpl):
            print(f"  → {pretty_path(render_html(doc))}")
        else:
            print("  （未找到 assets/dashboard_template.html，跳过页面生成）")
    warn_legacy_artifacts()


def warn_legacy_artifacts():
    """skill 目录里躺着旧版产物时提醒一句。

    产物换落点之后，读的是新位置；旧文件留在原地不会报错，只会让人以为
    「明明扫过却看不到」。这里只提示，不动手删。
    """
    legacy = [p for p in (legacy_artifact_paths() + tuple(
        sorted(globmod.glob(os.path.join(BASE, "plan-*")))))
        if os.path.exists(p)]
    if not legacy:
        return
    more = f" 等 {len(legacy)} 个" if len(legacy) > 1 else ""
    print(f"  注意：skill 目录里还有旧产物 {pretty_path(legacy[0])}{more}。"
          f"产物已改落 {pretty_path(artifact_root())}，确认后自行删除旧的。")


def render_html(doc):
    with open(os.path.join(BASE, "assets", "dashboard_template.html"), "r", encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = artifact_html()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__SKILL_DATA__*/null", payload))
    return out


def do_check(args):
    doc = load_json(artifact_json())
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    q = args.name.lower()
    hits = [e for e in doc["entities"] if e["name"].lower() == q] or \
           [e for e in doc["entities"] if q in e["name"].lower()]
    if not hits:
        print(f"没找到匹配「{args.name}」的 skill", file=sys.stderr)
        return 1
    for e in hits[:5]:
        print(f"\n{'=' * 72}\n{e['name']}   [{e['verdict'].upper()}]")
        print(f"  实体路径: {e['real_path']}")
        print(f"  类型: {e['type']}  ({e['type_evidence']})"
              f"{'  · 自动生成' if e['auto_created'] else ''}")
        print(f"  引用: 直接持有 {', '.join(e['entity_agents']) or '-'}"
              f" | 软链 {', '.join(e['link_agents']) or '-'}")
        print(f"  体量: {e['file_count']} 文件 / {human_bytes(e['total_bytes'])}")
        # overrides.json 里写了什么，这里就得回报什么 —— 否则「人工覆盖表」是单向的
        if e.get("override_note") or e.get("overrides_applied"):
            bits = []
            if e.get("overrides_applied"):
                bits.append("生效: " + ", ".join(e["overrides_applied"]))
            if e.get("override_note"):
                bits.append("说明: " + e["override_note"])
            print("  人工覆盖 → " + "  |  ".join(bits))
        if e["description"]:
            print(f"  描述: {e['description'][:160]}")
        if not e["checks"]:
            print("  校验: 全部通过")
        for c in e["checks"]:
            print(f"  [{c['level'].upper()}] {c['label']} × {c['count']}")
            for ev in c["evidence"]:
                loc = f"{ev['file']}:{ev['line']}" if ev["line"] else ev["file"]
                print(f"        {loc}  {ev['text']}")
    return 0


def do_install(args):
    doc = load_json(artifact_json())
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    hits = [e for e in doc["entities"] if e["name"].lower() == args.name.lower()]
    if not hits:
        print(f"没找到 skill「{args.name}」", file=sys.stderr)
        return 1
    agents_cfg = load_json(os.path.join(BASE, "agents.json"))
    rules_cfg = load_json(os.path.join(BASE, "rules.json")) or {}
    install_rules = [r for r in (rules_cfg.get("rules") or [])
                     if r.get("scope") == "install"]
    entity = hits[0]
    if args.to:
        targets = [a for a in agents_cfg["agents"] if a["id"] == args.to]
        if not targets:
            print(f"适配表里没有 agent「{args.to}」，可选："
                  + ", ".join(a["id"] for a in agents_cfg["agents"]), file=sys.stderr)
            return 1
    else:
        targets = [a for a in agents_cfg["agents"] if a["id"] not in entity["agents"]]
    for a in targets:
        held = a["id"] in entity["agents"]
        print(build_install_text(entity, a, agents_cfg, install_rules))
        if held:
            how = "实体持有" if a["id"] in entity["entity_agents"] else "软链引用"
            print(f"注意：{a['label']} 已以「{how}」方式持有该 skill，以上指令仅供参照。\n")
        else:
            print()
    return 0


# ---------------------------------------------------------------- 处理方案包

def build_plan(doc, agents_cfg, names=None, include_grades=("auto",)):
    """把选中的冲突编译成一份可复核、可干跑、可回滚的处理方案。

    产出两份东西：
      plan-<时间戳>.md  —— 给人看的清单：留哪份、为什么、会影响谁
      plan-<时间戳>.sh  —— 给机器跑的脚本：默认 DRY_RUN=1，什么都不改
    """
    # 时间戳要三处一致：文件名、脚本里的 TRASH/CANON_TS、清单里的「生成时间」。
    # 清单曾经印的是快照时间，跟文件名差着一次 scan 的距离，按清单去 trash 找会对不上。
    now = datetime.now(timezone(timedelta(hours=8)))
    ts = now.strftime("%Y%m%d-%H%M%S")
    picked = []
    for c in doc.get("conflicts") or []:
        if c["nature"] != "duplicate" or c["liveness"] == "dormant":
            continue
        if c["prescription"]["grade"] not in include_grades:
            continue
        if names and c["name"] not in names:
            continue
        picked.append(c)
    md = [f"# Skill 冲突处理方案",
          f"",
          f"生成时间：{now.isoformat(timespec='seconds')}　主机：{doc['host']}",
          f"基于快照：{doc['generated_at']}（清单内容取自这份快照；重新扫描后请重新生成）",
          f"范围：{len(picked)} 组（仅含真重复且仍有副本在生效的冲突）",
          f"",
          f"> 脚本默认干跑，不会动任何文件。确认清单无误后把 `DRY_RUN=1` 改成 `DRY_RUN=0` 再执行。",
          f"> 标「可自动」的组会直接替换；标「半自动」的组需要额外设 `CONFIRM_SEMI=1` 才会动手。",
          f"> 所有被替换掉的副本都会先移进 `{pretty_path(trash_root())}/`，不删除，可随时还原。",
          f""]
    sh = ["#!/usr/bin/env bash",
          "# 由 skillctl.py plan 生成。默认干跑。",
          "set -uo pipefail",
          f'DRY_RUN="${{DRY_RUN:-1}}"',
          f'CONFIRM_SEMI="${{CONFIRM_SEMI:-0}}"',
          f'TRASH="{trash_root()}/plan-{ts}"',
          f'CANON_TS="{ts}"',
          'say(){ printf "%s\\n" "$*"; }',
          'run(){ if [ "$DRY_RUN" = "1" ]; then say "  [dry-run] $*"; else say "  [执行] $*"; "$@"; fi; }',
          'swap(){ # swap <现有副本路径> <正本路径>',
          '  local old="$1" canon="$2" name; name="$(basename "$old")"',
          '  if [ ! -e "$old" ]; then say "  跳过：$old 不存在"; return; fi',
          '  run mkdir -p "$TRASH"',
          '  run mv "$old" "$TRASH/$name"',
          '  run ln -s "$canon" "$old"',
          '}',
          '']
    for c in picked:
        p = c["prescription"]
        canon = p.get("canonical")
        md += [f"## {c['name']}", "",
               f"- 冲突类型：{KIND_LABEL.get(c['kind'], c['kind'])}"
               + (f"　版本 {' vs '.join(c['version_drift'])}" if c.get("version_drift") else ""),
               f"- 副本 {c['count']} 份，涉及 {', '.join(sorted({a for e in c['entities'] for a in e['agents']}))}",
               f"- **留作正本**：`{canon.replace(HOME, '~')}`",
               f"  - 理由：{p.get('canonical_why', '')}",
               f"- 其余副本改为指向正本的快捷方式："]
        for r in p.get("rewrite", []):
            md.append(f"  - `{r['path'].replace(HOME, '~')}`（{', '.join(r['agents'])}）")
        if p.get("needs_diff"):
            if p.get("grade") == "semi":
                md += ["",
                       "  ⚠️ 这组正文一致但文件集不同，脚本已备好但默认不执行。",
                       "  先跑下面这条命令看清差在哪，确认没有你要保留的独有文件后，再用 `CONFIRM_SEMI=1` 重跑脚本：",
                       "  ```bash",
                       f"  diff -ru '{canon}' '{p['rewrite'][0]['path'] if p.get('rewrite') else ''}' | head -200",
                       "  ```"]
            else:
                md += ["",
                       "  ⚠️ 这组正文已不一致，脚本**不会**触碰它。请先跑对比命令人工定夺留哪份，再手写替换：",
                       "  ```bash",
                       f"  diff -ru '{canon}' '{p['rewrite'][0]['path'] if p.get('rewrite') else ''}' | head -200",
                       "  ```"]
        md.append("")
        grade = p.get("grade")
        if grade == "auto":
            # 逐字一致，直接换，无需额外确认
            sh.append(f"# ---- {c['name']}: 留 {canon.replace(HOME,'~')} ----")
            for r in p.get("rewrite", []):
                sh.append(f'swap "{r["path"]}" "{canon}"')
            sh.append("")
        elif grade == "semi":
            # 正文一致但文件集不同：脚本已备好，但要显式解闸才会执行
            sh.append(f"# ---- {c['name']}: 留 {canon.replace(HOME,'~')}（半自动，需 CONFIRM_SEMI=1）----")
            sh.append(f'if [ "$CONFIRM_SEMI" = "1" ]; then')
            for r in p.get("rewrite", []):
                sh.append(f'  swap "{r["path"]}" "{canon}"')
            sh.append("else")
            sh.append(f'  say "  跳过 {c["name"]}：半自动组，请先人工确认文件差异，再设 CONFIRM_SEMI=1 重跑"')
            sh.append("fi")
            sh.append("")
    sh.append('say ""')
    sh.append('say "完成。回滚方式：把 $TRASH 里的目录移回原位即可。"')
    md += ["---", "",
           "## 回滚", "",
           f"把 `{pretty_path(trash_root())}/plan-{ts}/` 里的目录移回原位即可。",
           f"本次动作同时记入 `{pretty_path(ledger_path())}`。"]
    os.makedirs(artifact_root(), exist_ok=True)
    md_path = os.path.join(artifact_root(), f"plan-{ts}.md")
    sh_path = os.path.join(artifact_root(), f"plan-{ts}.sh")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(sh_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sh) + "\n")
    os.chmod(sh_path, 0o755)
    auto = sum(1 for c in picked if c["prescription"]["grade"] == "auto")
    semi = sum(1 for c in picked if c["prescription"]["grade"] == "semi")
    manual = sum(1 for c in picked if c["prescription"]["grade"] == "manual")
    return {"md": md_path, "sh": sh_path, "groups": len(picked),
            "auto": auto, "semi": semi, "manual": manual}


def parse_canonical_arg(spec):
    """把 `--canonical "组名=路径,组名2=路径"` 解成 {组名: 路径}。

    路径里可能有逗号（少见但合法），所以只按**第一个** = 切分，剩下的整段当路径。
    """
    out = {}
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"--canonical 要写成 组名=路径 的形式，收到：{chunk}")
        name, path = chunk.split("=", 1)
        out[name.strip()] = expand(path.strip())
    return out


def do_resolve(args):
    """一键去重。页面上的按钮和这里走的是同一条实现路径。"""
    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    names = None
    if getattr(args, "names", None):
        names = {x.strip() for x in args.names.split(",") if x.strip()}
    try:
        canon_map = parse_canonical_arg(getattr(args, "canonical", None))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    dry = not getattr(args, "yes", False)
    log, ops, groups, skipped, warnings = resolve_conflict(
        doc, agents_cfg, names=names,
        allow_semi=bool(getattr(args, "semi", False)), dry_run=dry,
        canonical_map=canon_map)
    if not groups:
        print("没有可处理的重复冲突。")
    else:
        print("干跑预览（一个字节都没动）：" if dry else "已执行：")
        for ln in log:
            print(f"  {ln}")
        print()
        for g in groups:
            print(f"  {g['name']}　正本留在 {pretty_path(g['canonical'])}"
                  + ("（你指定的）" if g.get("human_picked") else ""))
            for f in g["from"]:
                print(f"    {pretty_path(f['path'])} → 改为快捷方式"
                      f"（原副本在 {pretty_path(f['trash'])}）")
        if dry:
            picked_names = ",".join(g["name"] for g in groups)
            canon_arg = ""
            if canon_map:
                canon_arg = ' --canonical "' + ",".join(
                    f"{g['name']}={g['canonical']}" for g in groups
                    if g.get("human_picked")) + '"'
            print()
            print(f"确认无误后加 --yes 重跑："
                  f"skillctl.py resolve --names {picked_names}{canon_arg} --yes")
    for s in skipped:
        print(f"[跳过] {s['name']}：{s['why']}", file=sys.stderr)
    for w in warnings:
        print(f"[注意] {w}", file=sys.stderr)
    return 0


def do_dismiss(args):
    """把冲突组标成「都先留着，别再提醒」（或取消标记）。"""
    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    names = [x.strip() for x in (args.names or "").split(",") if x.strip()]
    if not names:
        print("要指定组名：--names a,b", file=sys.stderr)
        return 1
    known = {c["name"] for c in (doc.get("conflicts") or [])}
    unknown = [n for n in names if n not in known]
    if unknown:
        # 名字打错就等于静默写进一条永远匹配不上的配置，趁早拦下来。
        print(f"这些名字不在当前冲突清单里：{', '.join(unknown)}", file=sys.stderr)
        return 1
    ignore = not getattr(args, "undo", False)
    dry = not getattr(args, "yes", False)
    for n in names:
        log, _ = set_conflict_ignore(n, note=getattr(args, "note", "") or "",
                                     ignore=ignore, dry_run=dry)
        for ln in log:
            print(f"  {ln}")
    if dry:
        print()
        print(f"确认后加 --yes 重跑：skillctl.py dismiss --names {','.join(names)}"
              + ("" if ignore else " --undo") + " --yes")
    else:
        print(f"\n已写入 {pretty_path(os.path.join(BASE, 'overrides.json'))}，"
              f"重跑 scan 后这一组不再计入待处理。")
    return 0


def do_undo(args):
    """撤销上一次「一键去重」。"""
    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    dry = not getattr(args, "yes", False)
    log, ops, info, skipped, warnings = undo_resolve(
        doc, at=getattr(args, "at", None), dry_run=dry)
    if info.get("error"):
        print(info["error"], file=sys.stderr)
        if info.get("hint"):
            print(info["hint"], file=sys.stderr)
        return 1
    if not info.get("groups"):
        print("这次操作里没有可还原的条目。")
    else:
        print("干跑预览（一个字节都没动）：" if dry else "已还原：")
        for ln in log:
            print(f"  {ln}")
        print()
        print(f"按台账回到 {info.get('at')} 之前的状态：")
        for g in info["groups"]:
            print(f"  {g['name']}　快捷方式已撤掉 {len(g['restored'])} 处，目录搬回原位")
            for r in g["restored"]:
                print(f"    {pretty_path(r['trash'])} → {pretty_path(r['path'])}")
    for s in skipped:
        print(f"[跳过] {s['name']}：{s['why']}", file=sys.stderr)
    for w in warnings:
        print(f"[注意] {w}", file=sys.stderr)
    return 0


KIND_LABEL = {"identical": "逐字一致", "meta-only": "仅元数据不同",
              "same-body-diff-files": "正文一致·文件集不同", "divergent": "正文已不一致"}


# ---------------------------------------------------------------- CLI 命令

def _load_all():
    doc = load_json(artifact_json())
    agents_cfg = load_json(os.path.join(BASE, "agents.json")) or {"agents": []}
    validate_agents_config(agents_cfg)
    return doc, agents_cfg


def do_state(args):
    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    hits = [e for e in doc["entities"] if args.name.lower() in e["name"].lower()]
    if not hits:
        print(f"没找到匹配「{args.name}」的 skill", file=sys.stderr)
        return 1
    meta = {a["id"]: a for a in doc["agent_stats"]}
    stale, newest = stale_toggle_source(agents_cfg, artifact_json())
    if stale:
        print(f"⚠️  开关文件已经比扫描结果新（{newest.replace(HOME, '~')}），"
              f"下面显示的是上一次 scan 的状态。重跑 `skillctl.py scan` 才会刷新。",
              file=sys.stderr)
    for e in hits[:5]:
        print(f"\n{'=' * 72}\n{e['name']}   总状态：{STATE_LABEL_CN.get(e['overall_state'], e['overall_state'])}")
        print(f"  真实副本: {e['real_path'].replace(HOME, '~')}")
        for r in e["refs"]:
            mark = {"on": "✔", "model_off": "◐", "off": "✘"}.get(r.get("state"), "?")
            how = "快捷方式" if r["is_link"] else "本体"
            print(f"    {mark} {r['agent']:<10} {how:<6} {r.get('state_label', ''):<10}"
                  f" {r['path'].replace(HOME, '~')}")
            if r.get("state_source"):
                print(f"        ← {r['state_source']}")
    return 0


STATE_LABEL_CN = {"on": "启用", "model_off": "仅手动可用", "partial_model_off": "部分副本仅手动可用",
                  "partial_off": "部分副本已禁用", "off": "已禁用"}


def _do_write_action(args, action):
    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    _ALL_ENTITIES[:] = doc["entities"]
    try:
        if action == "uninstall":
            log, warns, ops = uninstall_entity(doc, agents_cfg, args.name, args.agent,
                                               force=getattr(args, "force", False),
                                               dry_run=not args.yes)
            for w in warns:
                print(f"⚠️  {w}", file=sys.stderr)
        else:
            log, ops = do_set_state(doc, agents_cfg, args.name, args.agent, action,
                                    dry_run=not args.yes)
            for o in ops:
                if o.get("blast"):
                    print(f"⚠️  {o['blast']}", file=sys.stderr)
    except (ValueError, RuntimeError) as exc:
        print(f"已拒绝：{exc}", file=sys.stderr)
        return 2
    print(f"{'干跑预览' if not args.yes else '已执行'}：{action} {args.name} @ {args.agent}")
    for line in log:
        print("  " + line)
    if not args.yes:
        print("\n以上为干跑，未改动任何文件。确认无误后加 --yes 真正执行。")
    else:
        print("\n已落盘。state / check / 页面读的都是上一次 scan 的快照，"
              "重跑 `skillctl.py scan` 才会反映这次改动。")
    return 0


def do_disable(args):
    return _do_write_action(args, "disable")


def do_enable(args):
    return _do_write_action(args, "enable")


def do_uninstall(args):
    return _do_write_action(args, "uninstall")


def do_restore(args):
    """从回收站还原。args.path 可以是回收站条目路径，也可以是最后一条记录。"""
    led = load_ledger()
    if args.list or not args.path:
        acts = [a for a in led.get("actions", []) if a["action"] == "uninstall"]
        if not acts:
            print("回收站台账里没有卸载记录。")
            return 0
        print(f"{'时间':<20} {'skill':<28} {'agent':<10} 回收站位置")
        print("-" * 100)
        for a in acts[-40:]:
            for o in a.get("ops", []):
                if o.get("dst"):
                    print(f"{a['at']:<20} {a['name']:<28} {a['agent']:<10} "
                          f"{str(o['dst']).replace(HOME, '~')}")
        return 0
    src, dst = expand(args.path), None
    if not os.path.exists(src):
        print(f"回收站里没有：{args.path}", file=sys.stderr)
        return 1
    for a in reversed(led.get("actions", [])):
        for o in a.get("ops", []):
            if o.get("dst") and os.path.normpath(expand(o["dst"])) == os.path.normpath(src):
                dst = o.get("_orig") or None
    print(f"从 {args.path} 还原 → 需要手工确认目标位置。")
    print(f"实际路径：{src}")
    print("提示：确认无误后直接 `mv <回收站路径> <原位>` 即可，工具不代劳这一步。")
    return 0


def do_plan(args):
    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    if args.grades:
        grades = tuple(x.strip() for x in args.grades.split(",") if x.strip())
    elif args.auto_only:
        grades = ("auto",)
    else:
        grades = ("auto", "semi")
    names = set(args.names.split(",")) if args.names else None
    r = build_plan(doc, agents_cfg, names=names, include_grades=grades)
    print(f"处理方案包已生成：")
    print(f"  清单  {pretty_path(r['md'])}   （{r['groups']} 组："
          f"可自动 {r['auto']}　半自动 {r['semi']}　需人工 {r['manual']}）")
    print(f"  脚本  {pretty_path(r['sh'])}   （默认干跑，DRY_RUN=0 才真跑）")
    return 0


def do_agents(args):
    agents_cfg = load_json(os.path.join(BASE, "agents.json")) or {"agents": []}
    doc = load_json(artifact_json())
    stats = {s["id"]: s for s in (doc or {}).get("agent_stats", [])}
    print(f"{'id':<10} {'名称':<20} {'注册':>4} {'快捷':>4} {'自有':>4}  {'快捷方式':<8} {'开关粒度':<8} 开关落点")
    print("-" * 118)
    for a in agents_cfg["agents"]:
        s = stats.get(a["id"], {})
        sup = a.get("supports_symlink")
        sup = "支持" if sup is True else ("不支持" if sup is False else "未知")
        tg = a.get("toggle") or {}
        gran = {"skill": "技能级", "plugin": "插件级", "none": "无原生"}.get(
            tg.get("granularity"), "—")
        store = toggle_store_label(tg)
        print(f"{a['id']:<10} {a['label']:<20} {s.get('entries', '-'):>4} "
              f"{s.get('links', '-'):>4} {s.get('owned_entities', '-'):>4}  {sup:<8} {gran:<8} "
              f"{str(store).replace(HOME, '~')}")
    print()
    for e in agents_cfg.get("excluded", []):
        print(f"  已排除 {e['path']} — {e['reason']}")
    return 0


# ---------------------------------------------------------------- 直连服务

SERVE_HTML_MARKER = "/*__SERVER__*/null"


def allowed_origins(port):
    """直连服务允许跨域读取的来源白名单 —— 只有本机回环的几个写法。

    为什么不是 `*`：`GET /` 会把本次会话的令牌内联进页面再返回。若响应带
    `Access-Control-Allow-Origin: *`，用户浏览的任意网页都能跨域 fetch 这个回环地址、
    从响应体里读出令牌，再带令牌 POST `apply=true` 触发禁用/卸载。
    页面本身就是从这个回环地址发出的（同源），所以只放行回环来源就够用。
    """
    return {f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}"}


def origin_allowed(origin, port):
    """这个来源能不能跨域读响应体 —— 只看它是不是本机回环。

    刻意做成「由调用方传 port」的纯函数，而不是读挂在 server 上的白名单属性：
    属性式的写法一旦漏挂（比如忘了在 serve 里赋值）就是静默地谁都不放行，
    而这里端口直接取自真实监听端口，挂不挂都不影响判定。
    """
    return bool(origin) and origin in allowed_origins(port)


def make_handler(docbox, agents_cfg, token, html_path):
    import http.server
    import socketserver

    def fresh():
        """每次请求都按磁盘现状取数据 —— 否则在终端重扫之后，页面还在用进程启动时的旧快照。"""
        p = artifact_json()
        try:
            if os.path.getmtime(p) > docbox.get("mtime", 0):
                latest = load_json(p)
                if latest:
                    docbox["doc"] = latest
                    docbox["mtime"] = os.path.getmtime(p)
        except OSError:
            pass
        return docbox["doc"]

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "skillctl"

        def log_message(self, fmt, *a):
            sys.stderr.write("[skillctl] " + (fmt % a) + "\n")

        def _cors(self):
            """只回显本机回环来源；其它来源一律不给跨域读的许可。

            这里的判断是「读得到读不到」的边界，不是权限边界 —— 令牌校验仍然只在
            do_POST 里做（见 allowed_origins 的说明）。
            """
            origin = self.headers.get("Origin")
            if origin_allowed(origin, self.server.server_address[1]):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Skillctl-Token")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/index.html"):
                with open(html_path, "r", encoding="utf-8") as f:
                    tpl = f.read()
                payload = json.dumps({"base": f"http://127.0.0.1:{self.server.server_address[1]}",
                                      "token": token, "pid": os.getpid()},
                                     ensure_ascii=False)
                body = tpl.replace(SERVE_HTML_MARKER, payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                # 这一份 HTML 内联了本次会话的令牌，不许落进任何缓存
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.end_headers()
                self.wfile.write(body)
                return
            self._json({"ok": False, "error": "not found"}, 404)

        def do_POST(self):
            if self.headers.get("X-Skillctl-Token") != token:
                self._json({"ok": False, "error": "token 不匹配 —— 请从 serve 输出的地址打开页面"}, 403)
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except (ValueError, OSError):
                self._json({"ok": False, "error": "请求体不是合法 JSON"}, 400)
                return
            action = req.get("action")
            name = req.get("name")
            agent_id = req.get("agent")
            apply_now = bool(req.get("apply"))
            doc = fresh()
            _ALL_ENTITIES[:] = doc["entities"]
            try:
                if action in ("disable", "enable"):
                    log, ops = do_set_state(doc, agents_cfg, name, agent_id, action,
                                            dry_run=not apply_now)
                    self._json({"ok": True, "ops": ops, "log": log,
                                "dry_run": not apply_now,
                                "blast": next((o.get("blast") for o in ops if o.get("blast")), None)})
                elif action == "uninstall":
                    log, warns, ops = uninstall_entity(doc, agents_cfg, name, agent_id,
                                                   force=bool(req.get("force")),
                                                   dry_run=not apply_now)
                    self._json({"ok": True, "ops": ops, "log": log, "warnings": warns,
                                "dry_run": not apply_now})
                elif action == "plan":
                    names = set(req.get("names") or []) or None
                    grades = tuple(req.get("grades") or ["auto", "semi"])
                    r = build_plan(doc, agents_cfg, names=names, include_grades=grades)
                    self._json({"ok": True,
                                "log": [f"已生成处理方案包：{r['groups']} 组"
                                        f"（可自动 {r['auto']}　半自动 {r['semi']}　需人工 {r['manual']}）",
                                        f"清单  {r['md']}",
                                        f"脚本  {r['sh']}  —— 默认干跑，改 DRY_RUN=0 才真跑"],
                                "md": r["md"], "sh": r["sh"]})
                elif action == "resolve-conflict":
                    names = set(req.get("names") or []) or None
                    raw_map = req.get("canonical_map") or {}
                    if not isinstance(raw_map, dict):
                        raise ValueError("canonical_map 必须是 {组名: 路径}")
                    log, ops, groups, skipped, warns = resolve_conflict(
                        doc, agents_cfg, names=names,
                        allow_semi=bool(req.get("allow_semi")),
                        dry_run=not apply_now,
                        canonical_map={str(k): expand(str(v))
                                       for k, v in raw_map.items()})
                    self._json({"ok": True, "ops": ops, "log": log,
                                "groups": groups, "skipped": skipped,
                                "warnings": warns, "dry_run": not apply_now,
                                "undo": last_undoable() if apply_now else None})
                elif action == "dismiss-conflict":
                    names = [str(x) for x in (req.get("names") or [])]
                    known = {c["name"] for c in (doc.get("conflicts") or [])}
                    unknown = [n for n in names if n not in known]
                    if not names or unknown:
                        # 名字对不上就等于写进一条永远匹配不上的配置，必须拦下。
                        self._json({"ok": False, "error":
                                    f"这些名字不在当前冲突清单里：{', '.join(unknown) or '(空)'}"}, 400)
                        return
                    ignore = bool(req.get("ignore", True))
                    logs = []
                    for n in names:
                        lg, _ = set_conflict_ignore(
                            n, note=str(req.get("note") or ""), ignore=ignore,
                            dry_run=not apply_now)
                        logs.extend(lg)
                    self._json({"ok": True, "log": logs, "dry_run": not apply_now,
                                "names": names, "ignore": ignore})
                elif action == "undo-resolve":
                    log, ops, info, skipped, warns = undo_resolve(
                        doc, at=req.get("at"), dry_run=not apply_now)
                    if info.get("error"):
                        self._json({"ok": False, "error": info["error"]}, 409)
                        return
                    self._json({"ok": True, "ops": ops, "log": log, "info": info,
                                "skipped": skipped, "warnings": warns,
                                "dry_run": not apply_now,
                                "undo": last_undoable() if apply_now else None})
                elif action == "rescan":
                    do_scan(argparse.Namespace(no_html=False))
                    self._json({"ok": True, "log": ["已重新扫描，刷新页面查看最新结果"]})
                else:
                    self._json({"ok": False, "error": f"未知动作 {action}"}, 400)
            except (ValueError, RuntimeError) as exc:
                self._json({"ok": False, "error": str(exc)}, 409)
            except Exception as exc:                      # noqa: BLE001
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    return Handler


def do_serve(args):
    import secrets
    import socket
    import socketserver
    import threading
    import webbrowser

    doc, agents_cfg = _load_all()
    if not doc:
        print(missing_snapshot_hint(), file=sys.stderr)
        return 1
    html_path = artifact_html()
    if not os.path.isfile(html_path):
        print(f"还没有页面（找的是 {pretty_path(html_path)}），先跑：skillctl.py scan",
              file=sys.stderr)
        return 1
    token = secrets.token_urlsafe(24)
    json_path = artifact_json()
    try:
        docbox = {"doc": doc, "mtime": os.path.getmtime(json_path)}
    except OSError:
        docbox = {"doc": doc, "mtime": 0}

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", args.port), make_handler(docbox, agents_cfg, token, html_path)) as srv:
        url = f"http://127.0.0.1:{srv.server_address[1]}/?token={token}"
        print(f"直连服务已启动（只绑本机回环，进程号 {os.getpid()}）")
        print(f"  {url}")
        print(f"  这次会话的一次性令牌：{token}")
        print(f"  所有写操作默认干跑；卸载一律先移入 {pretty_path(trash_root())}/")
        print(f"  Ctrl-C 停止。")
        if args.open:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="skillctl",
                                 description="本地 skill 管理器（扫描 / 校验 / 迁移 / 开关）")
    sub = ap.add_subparsers(dest="cmd")
    # 产物落点是全局选项：子命令前后都能写。两份 parser 都要挂，且子命令那份的默认值
    # 必须是 SUPPRESS —— argparse 解析子命令时在新建的命名空间里补默认值，再整体盖回
    # 父命名空间。默认值不压掉的话，`--out X scan` 里的 X 会被一个 None 抹掉。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", metavar="DIR", default=argparse.SUPPRESS, help=OUT_HELP)
    ap.add_argument("--out", metavar="DIR", help=OUT_HELP)

    p = sub.add_parser("scan", help="扫描 + 校验 + 生成产物", parents=[common])
    p.add_argument("--no-html", action="store_true", help="只生成 json")
    p.set_defaults(func=do_scan)
    p = sub.add_parser("check", help="查看单个 skill 的校验详情", parents=[common])
    p.add_argument("name")
    p.set_defaults(func=do_check)
    p = sub.add_parser("state", help="查看某个 skill 在各 agent 的启用状态", parents=[common])
    p.add_argument("name")
    p.set_defaults(func=do_state)
    p = sub.add_parser("install", help="生成安装指令", parents=[common])
    p.add_argument("name")
    p.add_argument("--to", help="目标 agent id，缺省列出所有尚未持有的 agent")
    p.set_defaults(func=do_install)
    p = sub.add_parser("agents", help="列出 agent 适配表（含开关机制）", parents=[common])
    p.set_defaults(func=do_agents)
    p = sub.add_parser("plan", help="生成冲突处理方案包（清单 + 脚本）", parents=[common])
    p.add_argument("--names", help="逗号分隔的冲突名，缺省全部")
    p.add_argument("--auto-only", action="store_true", help="只纳入可自动处理的组")
    p.add_argument("--grades", help="逗号分隔的处理级别，可选 auto/semi/manual（缺省 auto,semi）")
    p.set_defaults(func=do_plan)
    p = sub.add_parser("resolve", parents=[common],
                       help="把可自动的重复冲突落盘（留一份，其余换成快捷方式）")
    p.add_argument("--names", help="逗号分隔的冲突名，缺省全部可自动组")
    p.add_argument("--semi", action="store_true",
                   help="连半自动组一起处理（正文一致但文件集不同）")
    p.add_argument("--canonical", metavar="组名=路径,...",
                   help="指定某一组留哪一份（正文已分叉的组要靠它才动手）")
    p.add_argument("--yes", action="store_true", help="真正执行（缺省为干跑预览）")
    p.set_defaults(func=do_resolve)
    p = sub.add_parser("undo", parents=[common],
                       help="撤销上一次「一键去重」：撤掉快捷方式，目录搬回原位")
    p.add_argument("--at", metavar="时间戳前缀",
                   help="撤销哪一次（缺省为最近一次没撤过的）")
    p.add_argument("--yes", action="store_true", help="真正执行（缺省为干跑预览）")
    p.set_defaults(func=do_undo)
    p = sub.add_parser("dismiss", parents=[common],
                       help="把冲突组标成「都先留着，别再提醒」（写进 overrides.json）")
    p.add_argument("--names", required=True, help="逗号分隔的冲突名")
    p.add_argument("--note", help="为什么先留着，写给自己以后看")
    p.add_argument("--undo", action="store_true", help="取消标记（恢复提醒）")
    p.add_argument("--yes", action="store_true", help="真正执行（缺省为干跑预览）")
    p.set_defaults(func=do_dismiss)
    p = sub.add_parser("serve", help="起本地直连服务，页面按钮可直接执行", parents=[common])
    p.add_argument("--port", type=int, default=8799)
    p.add_argument("--open", action="store_true", help="自动打开浏览器")
    p.set_defaults(func=do_serve)

    for cmd, helptext in (("disable", "禁用某个 agent 下的 skill（写它自己的原生开关）"),
                          ("enable", "恢复启用"),
                          ("uninstall", "卸载（移入回收站，不删除）")):
        p = sub.add_parser(cmd, help=helptext, parents=[common])
        p.add_argument("name")
        p.add_argument("--agent", required=True, help="目标 agent id")
        p.add_argument("--yes", action="store_true", help="真正执行（缺省为干跑预览）")
        if cmd == "uninstall":
            p.add_argument("--force", action="store_true",
                           help="实体被别的 agent 引用时，连引用一起清理")
        p.set_defaults(func={"disable": do_disable, "enable": do_enable,
                             "uninstall": do_uninstall}[cmd])

    p = sub.add_parser("restore", help="查看回收站台账 / 还原指引", parents=[common])
    p.add_argument("path", nargs="?", help="回收站里的路径")
    p.add_argument("--list", action="store_true", help="列出全部卸载记录")
    p.set_defaults(func=do_restore)

    args = ap.parse_args()
    # 落点必须在任何命令之前定下来 —— 读快照和写快照必须落在同一个地方。
    set_artifact_root(getattr(args, "out", None))
    fn = getattr(args, "func", None)
    if not fn:
        # 不带子命令是用法错误，不能返回 0 —— 否则 `skillctl.py && 下一步`
        # 会一路往下走。帮助写 stderr，保持 stdout 干净。
        ap.print_help(sys.stderr)
        return 2
    try:
        return fn(args) or 0
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
