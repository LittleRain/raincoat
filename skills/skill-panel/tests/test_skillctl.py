#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill-panel 单元测试。

跑法（从任意目录）：

    python3 tests/test_skillctl.py

只读本 skill 自己的三个声明式配置表，外加对纯函数的行为断言 ——
不依赖网络，也不读写本机上任何 agent 的配置。真正跨 agent 的写操作属于集成测试，
在 tooling/tests/skill-panel.sh 里跑。
"""

import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "skillctl.py"
TEMPLATE = SKILL_DIR / "assets" / "dashboard_template.html"

_spec = importlib.util.spec_from_file_location("skillctl", SCRIPT)
skillctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skillctl)

SOURCE = SCRIPT.read_text(encoding="utf-8")


def load_json(name):
    with open(SKILL_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


AGENTS = load_json("agents.json")
RULES = load_json("rules.json")
OVERRIDES = load_json("overrides.json")

CONFIG_FILES = ("agents.json", "rules.json", "overrides.json")

# 目录名契约：住在 raincoat 的 skills/ 下时强制「目录名 == 技能名」；
# 导出成独立仓库后目录名由目标仓库决定（可能被改叫别的），
# 这时只要求两份清单彼此一致 —— 否则导出副本必然挂测试。
INSIDE_SKILLS_DIR = SKILL_DIR.parent.name == "skills"


# ------------------------------------------------------------------ 目录契约

class LayoutTests(unittest.TestCase):
    """脚本住在 scripts/，配置与产物在 skill 根 —— 改错了整套路径就全废。"""

    def test_base_resolves_to_skill_root_not_scripts_dir(self):
        self.assertEqual(Path(skillctl.BASE).resolve(), SKILL_DIR.resolve())

    def test_declarative_tables_live_at_skill_root(self):
        for name in CONFIG_FILES:
            with self.subTest(name=name):
                self.assertTrue((SKILL_DIR / name).is_file(), f"缺 {name}")

    def test_engine_lives_in_scripts_dir(self):
        self.assertEqual(SCRIPT.parent.name, "scripts")

    def test_entry_dir_is_where_the_entry_script_actually_is(self):
        """页面上的命令全是 `cd <ENTRY_DIR> && python3 skillctl.py …`。

        这里曾经指着 skill 根，页面上每条命令都是死链
        （can't open file '<skill>/skillctl.py'）。
        """
        self.assertEqual(Path(skillctl.ENTRY_DIR).resolve(), SCRIPT.parent.resolve())
        self.assertTrue(Path(skillctl.ENTRY_DIR, "skillctl.py").is_file())

    def test_dashboard_commands_are_built_in_one_place(self):
        """命令必须只经过模板里的 CLI() 拼装。

        各处自己拼 `cd ${TOOL} && ${PY} skillctl.py` 的时代出过一次错
        （TOOL 指向 skill 根），修完把入口收敛成一个函数，这条守着别再散回去。
        """
        lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
        offenders = [f"{i}: {ln.strip()[:90]}"
                     for i, ln in enumerate(lines, 1)
                     if "skillctl.py" in ln and "const CLI =" not in ln and "CLI(" not in ln]
        self.assertEqual(offenders, [], "这些地方绕过了 CLI() 自己拼命令，容易再拼错目录")

    def test_template_lives_in_assets_and_keeps_injection_marker(self):
        self.assertTrue(TEMPLATE.is_file(), "缺 assets/dashboard_template.html")
        self.assertIn("/*__SKILL_DATA__*/null", TEMPLATE.read_text(encoding="utf-8"))

    def test_three_required_files_present(self):
        for name in ("SKILL.md", "README.md", "skill.json"):
            with self.subTest(name=name):
                self.assertTrue((SKILL_DIR / name).is_file(), f"缺 {name}")

    def test_skill_json_shape(self):
        meta = load_json("skill.json")
        for key in ("name", "title", "description", "version",
                    "status", "visibility", "entry", "tags", "author"):
            with self.subTest(key=key):
                self.assertIn(key, meta)
        self.assertIn(meta["status"], ("draft", "beta"))
        self.assertIn(meta["visibility"], ("incubating", "internal"))
        self.assertEqual(meta["entry"], "SKILL.md")
        self.assertTrue(meta["tags"])

    def test_manifests_agree_on_the_skill_name(self):
        """两份清单必须说同一个名字 —— 这才是本 skill 自己的不变量。"""
        fm, _, _ = skillctl.parse_frontmatter(
            (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("name"), load_json("skill.json")["name"])

    def test_directory_name_matches_manifest_inside_raincoat(self):
        """住在 raincoat 的 skills/ 下时，目录名必须等于技能名。

        导出成独立仓库后目录名由目标仓库决定，所以这条只在 skills/ 布局下成立。
        """
        if not INSIDE_SKILLS_DIR:
            self.skipTest("不在 raincoat 的 skills/ 布局下（导出副本），目录名不参与断言")
        self.assertEqual(load_json("skill.json")["name"], SKILL_DIR.name)

    def test_no_absolute_personal_paths_in_tracked_sources(self):
        """换个人 clone 下来就得能跑，所以本 skill 自己的文件里不该有 /Users/<某人>。

        生成物与扫描数据（plan-*、*.html、data/、__pycache__）天然带本机路径，
        它们已被 .gitignore 排除，这里一并跳过。
        """
        pattern = re.compile(r"/Users/(?!\.\.\./|name/)[A-Za-z0-9_.-]+")
        offenders = []
        for path in sorted(SKILL_DIR.rglob("*")):
            if not path.is_file():
                continue
            parts = path.relative_to(SKILL_DIR).parts
            if path.suffix in (".pyc", ".html") or path.name.startswith("plan-"):
                continue
            if "data" in parts or "__pycache__" in parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8",
                                                         errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(SKILL_DIR)}:{lineno}")
        self.assertEqual(offenders, [], f"发现写死的本机路径: {offenders}")


# ------------------------------------------------------------------ 文档可跑

class DocumentationTests(unittest.TestCase):

    def test_skill_md_frontmatter_has_name_and_trigger_description(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        fm, _, _ = skillctl.parse_frontmatter(text)
        self.assertEqual(fm.get("name"), load_json("skill.json")["name"])
        description = fm.get("description") or ""
        self.assertGreater(len(description), 80, "description 太短，agent 判断不了触发时机")
        self.assertIn("Use when", description)

    def test_skill_md_references_only_existing_files(self):
        """自己也要过自己那条「引用的脚本文件不存在」规则。

        闸门与 skillctl 的 `broken-script-ref` 一致：只有出现在命令上下文里才算引用。
        散文里提一句 `scripts/xxx.py` 不算 —— 否则这条规则会大面积误报。
        """
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        text += "\n" + (SKILL_DIR / "README.md").read_text(encoding="utf-8")
        command_prefix = re.compile(r"^(?:python3?|node|bash|sh|zsh|\./)\s")

        missing, in_fence = [], False
        for raw in text.splitlines():
            if raw.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            stripped = raw.strip().lstrip("-*0123456789. ")
            runnable = in_fence or bool(command_prefix.match(stripped))
            if not runnable:
                continue
            for rel in re.findall(r"`((?:scripts|assets|references|tests|examples)/[\w./-]+)`", raw):
                if not (SKILL_DIR / rel).exists():
                    missing.append(rel)
        self.assertEqual(missing, [], f"文档引用了不存在的文件: {missing}")


# ------------------------------------------------------------------ agent 适配表

class AgentsConfigTests(unittest.TestCase):

    def test_real_config_passes_validation(self):
        skillctl.validate_agents_config(AGENTS)

    def test_ids_unique_and_roots_kinds_known(self):
        ids = [a["id"] for a in AGENTS["agents"]]
        self.assertEqual(len(ids), len(set(ids)))
        for agent in AGENTS["agents"]:
            with self.subTest(agent=agent["id"]):
                self.assertTrue(agent["label"])
                self.assertTrue(agent["roots"])
                for root in agent["roots"]:
                    self.assertIn(root["kind"], skillctl.KNOWN_ROOT_KINDS)

    def test_toggle_paths_are_tilde_or_absolute(self):
        for agent in AGENTS["agents"]:
            toggle = agent.get("toggle")
            if not isinstance(toggle, dict):
                continue
            path = toggle.get("file")
            if path:
                with self.subTest(agent=agent["id"]):
                    self.assertTrue(path.startswith("~") or path.startswith("/"), path)

    def test_writer_typo_is_rejected_not_silently_treated_as_json(self):
        """JSON 是默认分支 —— 写错 writer 若不报错，会改到不知哪个文件的键上。"""
        broken = {"agents": [{
            "id": "x", "label": "X",
            "roots": [{"path": "~/a", "kind": "user_skills"}],
            "toggle": {"granularity": "skill", "writer": "json_nestd",
                       "file": "~/f.json", "container": ["c"]},
        }]}
        with self.assertRaises(skillctl.ConfigError) as ctx:
            skillctl.validate_agents_config(broken)
        self.assertIn("json_nestd", str(ctx.exception))

    def test_unknown_value_mode_is_rejected(self):
        broken = {"agents": [{
            "id": "x", "label": "X",
            "roots": [{"path": "~/a", "kind": "user_skills"}],
            "toggle": {"granularity": "skill", "writer": "json_nested", "file": "~/f.json",
                       "container": ["c"], "value_mode": "objectfield"},
        }]}
        with self.assertRaises(skillctl.ConfigError):
            skillctl.validate_agents_config(broken)

    def test_unknown_root_kind_is_rejected(self):
        broken = {"agents": [{"id": "x", "label": "X",
                              "roots": [{"path": "~/a", "kind": "wild"}]}]}
        with self.assertRaises(skillctl.ConfigError):
            skillctl.validate_agents_config(broken)

    def test_json_writer_without_container_is_rejected(self):
        broken = {"agents": [{
            "id": "x", "label": "X",
            "roots": [{"path": "~/a", "kind": "user_skills"}],
            "toggle": {"granularity": "skill", "writer": "json_nested", "file": "~/f.json"},
        }]}
        with self.assertRaises(skillctl.ConfigError) as ctx:
            skillctl.validate_agents_config(broken)
        self.assertIn("container", str(ctx.exception))

    def test_duplicate_agent_id_is_rejected(self):
        broken = {"agents": [
            {"id": "x", "label": "X", "roots": [{"path": "~/a", "kind": "user_skills"}]},
            {"id": "x", "label": "Y", "roots": [{"path": "~/b", "kind": "user_skills"}]},
        ]}
        with self.assertRaises(skillctl.ConfigError):
            skillctl.validate_agents_config(broken)

    def test_empty_agents_is_rejected(self):
        with self.assertRaises(skillctl.ConfigError):
            skillctl.validate_agents_config({"agents": []})


# ------------------------------------------------------------------ 规则表

class RulesConfigTests(unittest.TestCase):

    # 带 if/elif 前缀，免得把注释里引用这个写法的句子也当成一条实现扫进来。
    implementation = set(re.findall(r'(?:if|elif) det == "([a-z_]+)"', SOURCE))

    def test_real_config_passes_validation(self):
        skillctl.validate_rules_config(RULES)

    def test_ids_unique_and_levels_valid(self):
        ids = [r["id"] for r in RULES["rules"]]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in RULES["rules"]:
            with self.subTest(rule=rule["id"]):
                self.assertIn(rule["level"], ("fail", "warn"))
                self.assertTrue(rule["label"])

    def test_every_entity_rule_detector_is_actually_dispatched(self):
        """文档里写了、代码里没有的规则等于撒谎。install 期的规则另有出口。"""
        undeclared = []
        for rule in RULES["rules"]:
            if rule.get("scope") == "install":
                continue
            if rule["detector"] not in self.implementation:
                undeclared.append(f"{rule['id']} → {rule['detector']}")
        self.assertEqual(undeclared, [], f"这些规则没有对应实现: {undeclared}")

    def test_declared_detector_whitelist_matches_the_source(self):
        """校验用的白名单必须恰好等于「源码里真有分支的」那批名字。

        只钉一边会漂：改了 dispatch 忘了改常量，合法规则被拒；改了常量忘了改
        dispatch，拼错的名字又被放行。两边对起来才有意义。

        install 期的规则不走实体校验那条 if/elif 链（它们由 install_note 按 id
        取用），所以白名单里会多出这一批 —— 一并纳入比较，否则这条会永远红。
        """
        install_detectors = {r["detector"] for r in RULES["rules"]
                             if r.get("scope") == "install"}
        self.assertEqual(skillctl.KNOWN_DETECTORS,
                         self.implementation | install_detectors,
                         "KNOWN_DETECTORS 与源码里真实 dispatch 的分支不一致")

    def test_unknown_detector_is_rejected_not_silently_skipped(self):
        """dispatch 是 if/elif 链，拼错的 detector 会掉进 else 拿到空证据。

        那条规则从此永远不报任何东西，而规则表里它明明写着 —— 这是比报错更贵
        的一种失败，因为没人会去查一条「从来没命中过」的规则。
        """
        cfg = {"rules": [{"id": "typo-rule", "level": "warn", "kind": "other",
                          "label": "拼错的", "detector": "regex_linez"}]}
        with self.assertRaises(skillctl.ConfigError) as ctx:
            skillctl.validate_rules_config(cfg)
        self.assertIn("regex_linez", str(ctx.exception))

    def test_install_scope_rules_are_consumed_by_the_install_path(self):
        """install 期规则的 id 必须真能被 install_note 取到 —— 连字符写成下划线就取不到。"""
        install_rules = [r for r in RULES["rules"] if r.get("scope") == "install"]
        self.assertTrue(install_rules, "样例里应至少有一条 install 期规则")
        for rule in install_rules:
            with self.subTest(rule=rule["id"]):
                self.assertTrue(skillctl.install_note(install_rules, rule["id"]))

    def test_thresholds_are_positive_numbers(self):
        thresholds = RULES["thresholds"]
        self.assertTrue(thresholds)
        for key, value in thresholds.items():
            with self.subTest(key=key):
                self.assertIsInstance(value, (int, float))
                self.assertGreater(value, 0)

    def test_overrides_template_is_loadable_and_empty(self):
        self.assertIsInstance(OVERRIDES.get("by_entity"), dict)
        self.assertIsInstance(OVERRIDES.get("by_conflict"), dict)
        self.assertEqual(OVERRIDES["by_entity"], {}, "模板要干净：别再往模板里塞真条目")
        self.assertEqual(OVERRIDES["by_conflict"], {}, "模板要干净：别再往模板里塞真条目")


# ------------------------------------------------------------------ 凭据安全

# 凭据形状的样本一律按需拼接，绝不写成字面量。这样本文件里不存在任何一行
# 「键名 = 长随机值」，下面的自检才敢直接断言「零命中」，而不是给自己开例外。
#
# 这里踩过一次真坑：样本原本写成字面量、且用的是**真实**的 GitLab PAT，变量名又叫
# sample —— 恰好命中规则的整行豁免词 `\bsample\b`，于是自检全绿地把它放进了仓库，
# 最后是 GitHub secret scanning 在推送时拦下的。两个教训各自独立：
# 样本不能用真值；自检不能复用规则的放宽词表。
SAMPLE_KEY_NAME = "gitlab_" + "token"
SAMPLE_KEY_VALUE = "AbCd1234EfGh5678IjKl"


def sample_secret_line():
    """返回一行「键名 = 长随机值」形状的合成样本。"""
    return f'{SAMPLE_KEY_NAME} = "{SAMPLE_KEY_VALUE}"'


# 生成物不在交付面内，扫它们必然假阳性：仪表盘的职责就是把命中凭据的**原文**印出来当证据，
# 所以它含有凭据是设计如此。清单与 skills/skill-panel/.gitignore 里的条目一一对应。
GENERATED_DIRS = ("data", "__pycache__")
GENERATED_FILES = ("skill-panel.html",)
GENERATED_PREFIXES = ("plan-",)


def is_generated(rel):
    """rel 是相对 skill 根的 PurePosixPath。"""
    if any(part in GENERATED_DIRS for part in rel.parts):
        return True
    if rel.name in GENERATED_FILES:
        return True
    return rel.name.startswith(GENERATED_PREFIXES)


class SecretLiteralTests(unittest.TestCase):
    """这条规则管的是别人，所以更要先管住自己 —— 本 skill 是要开放出去的。"""

    def _secret_rule(self):
        return next(r for r in RULES["rules"] if r["id"] == "secret-literal")

    def test_patterns_flag_a_hardcoded_token(self):
        rule = self._secret_rule()
        hits = [p for p in rule["patterns"] if re.search(p, sample_secret_line())]
        self.assertTrue(hits, "凭据字面量没被检出，规则失效了")

    def test_allow_patterns_accept_env_reads_and_placeholders(self):
        rule = self._secret_rule()
        for sample in ('token = os.environ["MY_TOKEN"]',
                       'api_key = "${MY_API_KEY}"',
                       'secret = "<YOUR_SECRET>"',
                       'token = "xxx"',
                       'password = "redacted"'):
            with self.subTest(sample=sample):
                if any(re.search(a, sample) for a in rule["allow_patterns"]):
                    continue
                self.assertFalse(any(re.search(p, sample) for p in rule["patterns"]),
                                 f"显式占位/环境变量写法被误报: {sample}")

    def test_self_audit_is_not_defeated_by_broad_allow_words(self):
        """把曾经的失效模式钉住：变量名叫 sample，凭据就被整行豁免掉了。

        规则自己的 allow_patterns 是给「扫别人的仓库」用的，放宽是对的（别人的代码里
        满屏 your_token / dummy_secret）。但放宽带不进自检 —— 这里同时断言两件事：
        规则确实会豁免它（已知放宽），而自检走的 patterns-only 路径照样命中。
        """
        disguised = "sample = " + sample_secret_line()
        rule = self._secret_rule()
        self.assertTrue(any(re.search(a, disguised) for a in rule["allow_patterns"]),
                        "规则不再豁免 sample 行 —— 说明放宽词表变了，请复核本注释")
        self.assertTrue(any(re.search(p, disguised) for p in rule["patterns"]),
                        "自检路径漏掉了样本，回退成复用 allow_patterns 了")

    def test_own_files_contain_no_secret_literal(self):
        """零容忍：本 skill 的任何文件里都不许出现凭据形状，测试文件也不例外。

        刻意**不**复用 rule["allow_patterns"] —— 那张表是给扫别人的仓库用的，
        含 `\\bsample\\b` 这类整行豁免词，复用它就等于给自己留了后门（见文件头注释）。
        需要占位符时写 `${VAR}` 或 `<NAME>`，它们本来就不匹配 patterns。
        """
        rule = self._secret_rule()
        offenders = []
        for path in sorted(SKILL_DIR.rglob("*")):
            if not path.is_file() or path.name == "rules.json":
                continue  # rules.json 里是检测模式本身，不是凭据
            if path.suffix == ".pyc":
                continue
            rel = path.relative_to(SKILL_DIR)
            if is_generated(rel):
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8",
                                                         errors="ignore").splitlines(), 1):
                if any(re.search(p, line) for p in rule["patterns"]):
                    offenders.append(f"{rel.as_posix()}:{lineno}")
        self.assertEqual(offenders, [],
                         f"本 skill 的文件里检出疑似凭据（测试文件也不豁免）: {offenders}")

    def test_generated_skip_list_matches_gitignore(self):
        """自检跳过的生成物必须与 .gitignore 对齐，否则两边各自漂移。

        放宽了跳过范围就等于给凭据开后门；收窄了则会误报。
        忽略规则就在本 skill 根下（不是仓库根），这样导出成独立仓库时跟着走；
        也正因为只有这一份，这条测试才真的钉得住 —— 包括在导出副本里。
        """
        gitignore = SKILL_DIR / ".gitignore"
        self.assertTrue(gitignore.is_file(),
                        "本 skill 应自带 .gitignore，否则导出后生成物无人拦截")
        lines = [l.strip() for l in gitignore.read_text(encoding="utf-8").splitlines()]
        for entry in GENERATED_DIRS + GENERATED_FILES + GENERATED_PREFIXES:
            with self.subTest(entry=entry):
                self.assertTrue(any(entry in l for l in lines),
                                f".gitignore 未覆盖 {entry}，跳过清单已漂移")


# ------------------------------------------------------------------ frontmatter

class FrontmatterTests(unittest.TestCase):
    """块标量解析是降噪的地基：不支持它，「description 过短」会瞬间刷出上百条假阳性。"""

    def test_folded_block_scalar_is_joined_into_one_paragraph(self):
        fm, _, body = skillctl.parse_frontmatter(
            "---\nname: x\ndescription: >\n"
            "  第一行是很长很长很长很长很长的一行描述文字\n"
            "  第二行也是很长的描述文字内容\n"
            "---\n\n正文\n")
        self.assertIn("第一行", fm["description"])
        self.assertIn("第二行", fm["description"])
        self.assertGreater(len(fm["description"]), 30)
        self.assertNotIn("\n", fm["description"])
        self.assertEqual(body.strip(), "正文")

    def test_literal_block_scalar_keeps_newlines(self):
        fm, _, _ = skillctl.parse_frontmatter(
            "---\ndescription: |\n  第一行\n  第二行\n---\n")
        self.assertIn("\n", fm["description"])

    def test_quoted_scalar_is_unquoted(self):
        fm, _, _ = skillctl.parse_frontmatter('---\nname: "my-skill"\n---\n')
        self.assertEqual(fm["name"], "my-skill")

    def test_missing_frontmatter_returns_original_body(self):
        fm, raw, body = skillctl.parse_frontmatter("# 没有 frontmatter\n")
        self.assertEqual(fm, {})
        self.assertEqual(raw, "")
        self.assertEqual(body, "# 没有 frontmatter\n")

    def test_unterminated_frontmatter_is_not_half_parsed(self):
        fm, raw, _ = skillctl.parse_frontmatter("---\nname: x\n")
        self.assertEqual(fm, {})
        self.assertEqual(raw, "")

    def test_this_skill_descriptions_survive_parsing(self):
        """SKILL.md 与 skill.json 的描述不该互相打架。"""
        fm, _, _ = skillctl.parse_frontmatter(
            (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
        meta = load_json("skill.json")
        self.assertGreater(len(fm["description"]), 80)
        self.assertGreater(len(meta["description"]), 40)


# ------------------------------------------------------------------ 安装文本

class InstallTextTests(unittest.TestCase):

    @staticmethod
    def entity():
        return {"name": "demo", "real_path": "/tmp/demo", "link_count": 0,
                "link_agents": [], "checks": [],
                "deps": {"tools": [], "skills": [], "mcp": []}}

    def test_advisory_appears_only_when_symlink_support_is_unknown(self):
        install_rules = [r for r in RULES["rules"] if r.get("scope") == "install"]
        cases = {"unknown": (None, True), "yes": (True, False), "no": (False, False)}
        for label, (support, expect_advisory) in cases.items():
            with self.subTest(support=label):
                agent = {"id": "x", "label": "X", "supports_symlink": support,
                         "install_hint": "~/x/skills"}
                text = skillctl.build_install_text(self.entity(), agent, AGENTS, install_rules)
                self.assertEqual("提示:" in text, expect_advisory, text)

    def test_stream_symlink_offers_copy_fallback(self):
        agent = {"id": "x", "label": "X", "supports_symlink": True, "install_hint": "~/x/skills"}
        text = skillctl.build_install_text(self.entity(), agent, AGENTS, [])
        self.assertIn("ln -s", text)
        self.assertIn("cp -R", text)

    def test_blocking_checks_are_surfaced_before_executing(self):
        entity = self.entity()
        entity["checks"] = [{"level": "fail", "label": "缺少 SKILL.md", "evidence": []}]
        agent = {"id": "x", "label": "X", "supports_symlink": False, "install_hint": "~/x/skills"}
        text = skillctl.build_install_text(entity, agent, AGENTS, [])
        self.assertIn("FAIL", text)
        self.assertIn("缺少 SKILL.md", text)


# ------------------------------------------------------------------ 处方

class PrescriptionTests(unittest.TestCase):

    @staticmethod
    def ent(path, links=0, holders=(), mtime=0.0, kind="local", state="on",
            real=3, link=0, size=1000, exists=True):
        """一份副本。默认是一份普通、可用、有内容的副本，各参数用来把它改成各种坏样子。"""
        return {"real_path": path, "link_count": links, "entity_agents": list(holders),
                "agents": ["a"], "name": "dup", "type": kind, "state": state,
                "path_exists": exists, "real_file_count": real, "link_file_count": link,
                "mtime": mtime, "total_bytes": size, "file_count": real + link}

    def test_canonical_rank_picks_the_rule_that_matches_the_problem(self):
        """三种排序规则，按「这一组到底是什么问题」选。

        · 正文已分叉（time）：按「最近被动过」——本机实测 32 份冲突副本里状态不是启用的
          只有 3 份、引用数为 0 的有 28 份、版本号 21 份没有，只有时间既有区分度又讲得清。
        · 正文一致但文件集不同（content）：按「内容更全」。这一档按时间挑会挑中「更晚被
          复制过来」的那份，把多出来的文件推进回收站 —— 实测 e2e 里就踩到了。
        · 内容逐字一致（stable）：留哪份都不改内容，优先留在被多方引用的那份。
        """
        old = self.ent("/tmp/old", mtime=1000)
        new = self.ent("/tmp/new", mtime=2000)
        self.assertGreater(skillctl.canonical_rank(new, mode="time"),
                           skillctl.canonical_rank(old, mode="time"),
                           "分叉组里更新的副本应排在前面")
        # 半自动档：更旧但更全的那份必须赢过更新但残缺的那份
        fuller_but_older = self.ent("/tmp/full", mtime=1000, real=5, size=5000)
        newer_but_thin = self.ent("/tmp/thin", mtime=9999, real=1, size=200)
        self.assertGreater(skillctl.canonical_rank(fuller_but_older, mode="content"),
                           skillctl.canonical_rank(newer_but_thin, mode="content"),
                           "半自动组必须按内容更全挑，不能按时间挑")
        pooled = self.ent(os.path.join(os.path.expanduser("~"), ".agents", "skills", "d"),
                          mtime=1)
        solo = self.ent("/tmp/zzz", mtime=999999)
        self.assertGreater(skillctl.canonical_rank(pooled, mode="stable"),
                           skillctl.canonical_rank(solo, mode="stable"),
                           "内容一致的组里，共享池那份应排在前面（哪怕它更旧）")
        linked = self.ent("/tmp/xxxxx", mtime=1000, links=3)
        plain = self.ent("/tmp/x", mtime=1000)
        self.assertGreater(skillctl.canonical_rank(linked, mode="stable"),
                           skillctl.canonical_rank(plain, mode="stable"),
                           "同一时间戳时被引用多的应排在前面")
        self.assertGreater(skillctl.canonical_rank(self.ent("/tmp/bb", mtime=1000)),
                           skillctl.canonical_rank(self.ent("/tmp/aaaaaaaa", mtime=1000)),
                           "再并列时短路径兜底")
        # 内容一致的档里刻意不看时间：同一份家底在不同机器上要挑出同一个正本。
        self.assertEqual(skillctl.canonical_rank(self.ent("/tmp/aa", mtime=1), mode="stable"),
                         skillctl.canonical_rank(self.ent("/tmp/aa", mtime=99999),
                                                 mode="stable"))

    def test_recommendation_reason_matches_the_rule_that_was_used(self):
        """理由必须跟真正参与的判据一致 —— 说一个没参与判断的理由等于教人用错的判据。"""
        mine = self.ent("/tmp/full", mtime=1000, real=5, size=5000)
        other = self.ent("/tmp/thin", mtime=9999, real=1, size=200)
        note = skillctl.canonical_note(mine, [other], mode="content")
        self.assertIn("文件最全", note, f"半自动档该说内容更全，实际：{note}")
        self.assertNotIn("最近被动过", note, f"半自动档不该拿时间当理由，实际：{note}")
        fresh = self.ent("/tmp/new", mtime=9999999, real=1, size=200)
        note = skillctl.canonical_note(fresh, [mine], mode="time")
        self.assertIn("最近被动过", note, f"分叉档该说时间，实际：{note}")
        self.assertNotIn("文件最全", note, f"分叉档不该拿体量当理由，实际：{note}")

    def test_auto_repairable_only_when_every_replaced_copy_is_a_dangling_link(self):
        """「工具可自行修复」只在被替换的每一份后面都什么都没有时成立。

        这条判定是前后端共用的单一来源，判宽了就等于让工具替人做正文取舍。
        """
        canon = self.ent("/tmp/good", real=1)
        gone = {"real_path": "/tmp/gone", "agents": ["a"], "name": "dup",
                "type": "local", "state": "on", "path_exists": False,
                "link_at": ["/tmp/where-the-link-sits"], "real_file_count": 0,
                "link_file_count": 0, "mtime": 0.0, "total_bytes": 0,
                "file_count": 0, "link_count": 0, "entity_agents": []}
        out = skillctl.prescribe("divergent", "duplicate", "live", [canon, gone])
        self.assertTrue(out["auto_repairable"], out)

        real_other = self.ent("/tmp/other", real=1)
        out = skillctl.prescribe("divergent", "duplicate", "live",
                                 [canon, gone, real_other])
        self.assertFalse(out["auto_repairable"],
                         "还有一份真有正文的副本时，留哪份是人的取舍")

        out = skillctl.prescribe("divergent", "duplicate", "live", [canon, real_other])
        self.assertFalse(out["auto_repairable"], "没有断链就不该标记为可自行修复")

        # 软链农场不是断链：目录在、只是文件都是链 —— 那些链可能各自指向别处
        farm = dict(gone, path_exists=True, real_file_count=0, link_file_count=2)
        out = skillctl.prescribe("divergent", "duplicate", "live", [canon, farm])
        self.assertFalse(out["auto_repairable"], out)

    def test_unusable_copies_are_never_usable_candidates(self):
        """断链 / 空壳 / 软链农场 / 商店与内置 / 已停用，一律不能当正本。

        这是回归测试：本机 `find-skills` 一组的正本候选是 `~/.agents/skills/find-skills`，
        那条路径**不存在**（来源是 `~/.claude/skills/find-skills` 这个断链）。旧评分只看
        「路径在不在共享池」，把空气选成了正本 —— 照着它执行就把好副本换成指向空气的快捷方式。
        """
        cases = [
            (self.ent("/tmp/gone", exists=False), "不存在"),
            (self.ent("/tmp/empty", real=0, link=0), "没有文件"),
            (self.ent("/tmp/farm", real=0, link=7), "全是快捷方式"),
            (self.ent("/tmp/mkt", kind="market"), "技能商店"),
            (self.ent("/tmp/builtin", kind="builtin"), "内置"),
            (self.ent("/tmp/off", state="model_off"), "停用"),
        ]
        for entity, needle in cases:
            with self.subTest(path=entity["real_path"]):
                usable, why = skillctl.candidate_usable(entity)
                self.assertFalse(usable, f"{entity['real_path']} 不该可用")
                self.assertIn(needle, why, why)
        usable, why = skillctl.candidate_usable(self.ent("/tmp/fine", mtime=5))
        self.assertTrue(usable, why)
        self.assertEqual(why, "")

    def test_prescribe_skips_unusable_copies_when_picking_canonical(self):
        """只有一份可用时，正本就该是它 —— 哪怕别的副本「看起来更该留」。"""
        ents = [
            self.ent("/tmp/broken", exists=False, mtime=999999),      # 最新，但坏了
            self.ent("/tmp/market", kind="market", mtime=999998),      # 也很新，但是商店的
            self.ent("/tmp/real", real=4, mtime=100),
        ]
        result = skillctl.prescribe("divergent", "duplicate", "active", ents)
        self.assertEqual(result["canonical"], "/tmp/real")
        self.assertEqual(result["shape"], "broken")
        self.assertTrue(result["decidable"], "只剩一份可用，没什么可挑的")

    def test_scoring_reason_is_always_non_empty(self):
        for label in ("共享池", "App 包内", "普通副本"):
            with self.subTest(label=label):
                path = {"共享池": os.path.join(os.path.expanduser("~"), ".agents", "skills", "d"),
                        "App 包内": "/Applications/A.app/skills/d",
                        "普通副本": "/tmp/d"}[label]
                self.assertTrue(skillctl.canonical_note(self.ent(path, mtime=9), []))

    def test_prescription_grade_matrix(self):
        ents = [self.ent("/tmp/a", links=2, size=5000), self.ent("/tmp/b", size=4900)]
        expected = {"identical": "auto", "meta-only": "auto",
                    "same-body-diff-files": "semi", "divergent": "manual"}
        for kind, grade in expected.items():
            with self.subTest(kind=kind):
                result = skillctl.prescribe(kind, "duplicate", "active", ents)
                self.assertEqual(result["grade"], grade)
                self.assertTrue(result["rewrite"])
                # 「需人工」不再靠左右对比了 —— 页面上给的是选正本的卡片，所以只有半自动还需要看差异。
                self.assertEqual(result["needs_diff"], kind == "same-body-diff-files")

    def test_divergent_shapes_are_told_apart(self):
        """「正文不一致」要拆成四种形态，前三种不该让人做取舍。"""
        broken = [self.ent("/tmp/a", exists=False), self.ent("/tmp/b")]
        farm = [self.ent("/tmp/a", real=0, link=5), self.ent("/tmp/b")]
        shell = [self.ent("/tmp/shell", size=147), self.ent("/tmp/real", size=2187)]
        fork = [self.ent("/tmp/a", size=4246), self.ent("/tmp/b", size=4933)]
        for ents, shape in ((broken, "broken"), (farm, "symlink-farm"),
                            (shell, "shell"), (fork, "fork")):
            with self.subTest(shape=shape):
                result = skillctl.prescribe("divergent", "duplicate", "active", ents)
                self.assertEqual(result["shape"], shape)
                self.assertTrue(result["shape_sentence"], "每种形态都要有一句人话说明")
        # 转发壳不能当正本：它本来就不装内容，把内容并过去才对。但要在候选里说明原因，不静默剔除。
        result = skillctl.prescribe("divergent", "duplicate", "active", shell)
        self.assertEqual(result["canonical"], "/tmp/real")
        shell_row = [c for c in result["candidates"] if c["path"] == "/tmp/shell"][0]
        self.assertFalse(shell_row["usable"])
        self.assertIn("转发壳", shell_row["why"])
        self.assertEqual(len(result["candidates"]), 2, "候选要列全，人才能自己改主意")
        # 真分叉没有快捷答案
        self.assertFalse(skillctl.prescribe("divergent", "duplicate", "active", fork)["decidable"])

    def test_ignored_conflict_is_left_alone(self):
        """标了「都留着」的组不进待处理 —— 出口有没有用全看这里。"""
        ents = [self.ent("/tmp/a"), self.ent("/tmp/b")]
        result = skillctl.prescribe("divergent", "duplicate", "active", ents, ignored=True)
        self.assertEqual(result["grade"], "none")
        self.assertIn("不再提醒", result["action"])
        self.assertNotIn("rewrite", result)

    def test_conflict_ignores_reads_only_valid_entries(self):
        ov = {"by_conflict": {"keep-both": {"ignore": True, "note": "两份壳各喂一个 agent"},
                              "not-ignored": {"note": "只是备注"},
                              "junk": "不是字典"}}
        self.assertEqual(skillctl.conflict_ignores(ov),
                         {"keep-both": "两份壳各喂一个 agent"})
        self.assertEqual(skillctl.conflict_ignores({}), {})
        self.assertEqual(skillctl.conflict_ignores(None), {})

    def test_coexist_and_dormant_groups_are_left_alone(self):
        ents = [self.ent("/tmp/a"), self.ent("/tmp/b")]
        for nature, liveness in (("coexist", "active"), ("duplicate", "dormant")):
            with self.subTest(nature=nature, liveness=liveness):
                result = skillctl.prescribe("identical", nature, liveness, ents)
                self.assertEqual(result["grade"], "none")
                self.assertNotIn("rewrite", result)


# ------------------------------------------------------------------ 小工具

class UtilityTests(unittest.TestCase):

    def test_expand_handles_tilde(self):
        self.assertEqual(skillctl.expand("~/x"), os.path.join(os.path.expanduser("~"), "x"))

    def test_human_bytes_units(self):
        self.assertEqual(skillctl.human_bytes(512), "512B")
        self.assertEqual(skillctl.human_bytes(2048), "2.0KB")
        self.assertEqual(skillctl.human_bytes(3 * 1024 * 1024), "3.0MB")

    def test_sha_is_stable_and_accepts_bytes(self):
        self.assertEqual(skillctl.sha("abc"), skillctl.sha(b"abc"))
        self.assertNotEqual(skillctl.sha("abc"), skillctl.sha("abd"))

    def test_trash_lives_under_skill_panel_state_dir(self):
        path = skillctl.trash_path_for({"name": "eli5"}, "workbuddy")
        self.assertTrue(path.startswith(os.path.join(os.path.expanduser("~"),
                                                     ".skill-panel", "trash")))
        self.assertIn("workbuddy", path)

    def test_trash_path_keeps_hostile_names_inside_the_trash_root(self):
        """回收站路径由 skill 名拼出来，名字里带斜杠也绝不能逃出回收站。"""
        root = os.path.realpath(os.path.join(os.path.expanduser("~"),
                                            ".skill-panel", "trash"))
        for hostile in ("../../etc/passwd", "a/b", "x y", ".."):
            with self.subTest(name=hostile):
                path = skillctl.trash_path_for({"name": hostile}, "x")
                self.assertNotIn(os.sep, os.path.basename(path))
                self.assertTrue(os.path.realpath(os.path.dirname(path)).startswith(root),
                                f"{hostile!r} 逃出了回收站: {path}")


class StaleSnapshotTests(unittest.TestCase):
    """快照过期必须被说破：改完开关看不到变化时，人不该怀疑工具坏了。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.doc = self.root / "skills.json"
        self.doc.write_text("{}", encoding="utf-8")
        self.toggle = self.root / "settings.json"
        self.toggle.write_text("{}", encoding="utf-8")

    def config(self):
        return {"agents": [{
            "id": "x", "label": "X",
            "roots": [{"path": "~/a", "kind": "user_skills"}],
            "toggle": {"granularity": "skill", "writer": "json_nested",
                       "file": str(self.toggle), "container": ["skillOverrides"]},
        }]}

    def test_fresh_when_nothing_changed_after_the_scan(self):
        os.utime(self.toggle, (1_600_000_000, 1_600_000_000))
        os.utime(self.doc, (1_700_000_000, 1_700_000_000))
        stale, _ = skillctl.stale_toggle_source(self.config(), str(self.doc))
        self.assertFalse(stale)

    def test_stale_when_a_toggle_file_is_newer_than_the_scan(self):
        os.utime(self.toggle, (1_700_000_000, 1_700_000_000))
        os.utime(self.doc, (1_600_000_000, 1_600_000_000))
        stale, newest = skillctl.stale_toggle_source(self.config(), str(self.doc))
        self.assertTrue(stale)
        self.assertEqual(newest, str(self.toggle))

    def test_no_toggle_declared_is_never_stale(self):
        os.utime(self.doc, (1_600_000_000, 1_600_000_000))
        stale, newest = skillctl.stale_toggle_source({"agents": []}, str(self.doc))
        self.assertFalse(stale)
        self.assertIsNone(newest)

    def test_missing_scan_artifact_is_not_reported_as_stale(self):
        stale, _ = skillctl.stale_toggle_source(self.config(), str(self.root / "nope.json"))
        self.assertFalse(stale)


# ---------------------------------------------------------- 快照缺失的退出码

class SnapshotExitCodeTests(unittest.TestCase):
    """没有扫描产物时必须是非零退出。

    包装脚本、CI、`&&` 链都靠退出码判断，返回 0 会被读成「成功」。
    数退出码时别写成 `cmd | head` —— 那样拿到的是 head 的退出码，永远 0。
    """

    def setUp(self):
        self._orig_base = skillctl.BASE
        self._tmp = tempfile.mkdtemp()
        skillctl.BASE = self._tmp
        # 产物落点也得钉住：否则「没有快照」取决于跑测人 ~/.skill-panel 里有没有东西
        skillctl.set_artifact_root(self._tmp)
        # 只缺扫描快照，配置照旧 —— 否则先撞上「agents.json 缺失」，测不到这条。
        for name in CONFIG_FILES:
            shutil.copy(SKILL_DIR / name, Path(self._tmp) / name)
        self.assertFalse((Path(self._tmp) / "data" / "skills.json").exists())

    def tearDown(self):
        skillctl.BASE = self._orig_base
        skillctl.set_artifact_root(None)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _call(self, func, **kwargs):
        with contextlib.redirect_stderr(io.StringIO()):
            return func(argparse.Namespace(**kwargs))

    def test_snapshot_dependent_commands_return_one(self):
        cases = {
            "check": lambda: self._call(skillctl.do_check, name="anything"),
            "state": lambda: self._call(skillctl.do_state, name="anything"),
            "install": lambda: self._call(skillctl.do_install, name="anything"),
            "plan": lambda: self._call(skillctl.do_plan, grades=None,
                                       auto_only=False, names=None),
            "serve": lambda: self._call(skillctl.do_serve, port=8799, open=False),
            "disable": lambda: self._call(skillctl.do_disable, name="anything",
                                          agent="fakeagent", yes=False),
            "uninstall": lambda: self._call(skillctl.do_uninstall, name="anything",
                                            agent="fakeagent", yes=False, force=False),
        }
        for name, call in cases.items():
            with self.subTest(cmd=name):
                self.assertEqual(call(), 1, f"{name} 在无快照时应返回 1")

    def test_bare_invocation_is_a_usage_error(self):
        """不带子命令不是成功。帮助走 stderr，stdout 保持干净。"""
        saved = sys.argv
        sys.argv = ["skillctl.py"]
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = skillctl.main()
        finally:
            sys.argv = saved
        self.assertEqual(code, 2)
        self.assertIn("usage", err.getvalue().lower())

    def test_explicit_help_still_exits_zero(self):
        saved = sys.argv
        sys.argv = ["skillctl.py", "--help"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    skillctl.main()
        finally:
            sys.argv = saved
        self.assertEqual(caught.exception.code, 0)


# ---------------------------------------------------------- 导出成独立仓库

def _generated_only(directory, names):
    """导出副本里只去掉生成物。

    不能用 ignore_patterns("*.html") —— assets/dashboard_template.html 是模板**源**，
    少了它整个仪表盘就生成不出来。
    """
    skipped = []
    for name in names:
        if name in ("data", "__pycache__") or name.startswith("plan-"):
            skipped.append(name)
        elif name == "skill-panel.html" and Path(directory) == SKILL_DIR:
            skipped.append(name)
    return set(skipped)


class ExportPortabilityTests(unittest.TestCase):
    """导出成独立仓库后目录名由目标仓库决定，测试不能因此挂。

    回归用例：以前两处断言拿 SKILL_DIR.name 当基准，导出目录一改名就挂 2 个。
    """

    def test_own_suite_passes_in_a_differently_named_copy(self):
        if os.environ.get("SKILL_PANEL_NESTED_SELFTEST") == "1":
            self.skipTest("防递归：内层副本不再自我复制")
        if not INSIDE_SKILLS_DIR:
            self.skipTest("只从仓库内的原件发起自检")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "renamed-export"
            shutil.copytree(SKILL_DIR, dest, ignore=_generated_only)
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                cwd=dest, capture_output=True, text=True,
                env=dict(os.environ, SKILL_PANEL_NESTED_SELFTEST="1"))
            self.assertEqual(proc.returncode, 0,
                             f"改名后的副本里测试挂了：\n{proc.stderr[-2000:]}")


# ---------------------------------------------------------- Python 版本下限

def _annotation_expressions(tree):
    """产出这棵树里所有注解表达式（参数、返回值、变量注解）。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = (list(node.args.posonlyargs) + list(node.args.args)
                    + list(node.args.kwonlyargs))
            for extra in (node.args.vararg, node.args.kwarg):
                if extra is not None:
                    args.append(extra)
            for a in args:
                if a.annotation is not None:
                    yield a.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield node.annotation


class PythonFloorTests(unittest.TestCase):
    """SKILL.md 与 README 都承诺 Python 3.9+，所以代码必须真能在 3.9 上跑。

    回归用例：`def read_text(path: str, limit: int | None = None)` 里的 `int | None`
    是 PEP 604 写法，3.10 才有。注解在 def 时求值，于是 import 阶段就炸：

        TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'

    别人机器上的 `python3` 很可能就是系统自带的那一个（macOS 至今是 3.9.6），
    所以这不是学术问题 —— 同事 clone 下来第一条命令就跑不起来。
    用 AST 钉住，比在文档里写「请用 3.10」可靠：这条测试在任何版本上都跑得动。
    """

    def test_no_pep604_unions_in_annotations(self):
        offenders = []
        for path in sorted(SKILL_DIR.rglob("*.py")):
            parts = path.relative_to(SKILL_DIR).parts
            if "__pycache__" in parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for ann in _annotation_expressions(tree):
                for sub in ast.walk(ann):
                    if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                        rel = path.relative_to(SKILL_DIR)
                        offenders.append(f"{rel}:{sub.lineno}")
        self.assertEqual(offenders, [],
                         "注解里出现 PEP 604 的 `X | Y`（3.10+），3.9 会在 import 期抛 TypeError；"
                         f"改用 typing.Optional / typing.Union：{offenders}")

    def test_runtime_unions_in_assignments_are_absent(self):
        """`ALIAS = int | None` 这类运行期求值的联合，同样是 3.9 的 TypeError。"""
        offenders = []
        for path in sorted(SKILL_DIR.rglob("*.py")):
            parts = path.relative_to(SKILL_DIR).parts
            if "__pycache__" in parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for sub in ast.walk(node.value):
                    if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr) \
                            and isinstance(sub.left, ast.Name) \
                            and sub.left.id in ("int", "str", "float", "bool", "list", "dict", "tuple", "set"):
                        rel = path.relative_to(SKILL_DIR)
                        offenders.append(f"{rel}:{sub.lineno}")
        self.assertEqual(offenders, [], f"运行期类型联合在 3.9 上会抛 TypeError：{offenders}")


# ---------------------------------------------------------- 直连服务的来源边界

class ServeOriginTests(unittest.TestCase):
    """直连服务不能把带令牌的页面交给任意来源。

    `GET /` 的响应体内联了本次会话的令牌。响应头若写死
    `Access-Control-Allow-Origin: *`，用户浏览的任意网页都能跨域 fetch 这个回环地址、
    从响应体里读出令牌，再带令牌 POST `apply=true` 触发禁用/卸载 —— 令牌校验此时
    形同虚设。页面本来就从同一个回环地址发出（同源），所以只放行回环来源即可。
    """

    def test_whitelist_is_loopback_only(self):
        origins = skillctl.allowed_origins(8000)
        self.assertIn("http://127.0.0.1:8000", origins)
        self.assertIn("http://localhost:8000", origins)
        for bad in ("*", "null", "https://evil.example", "http://evil.example:8000",
                    "http://192.168.1.5:8000", "http://127.0.0.1:8001"):
            with self.subTest(origin=bad):
                self.assertNotIn(bad, origins)

    def test_origin_allowed_is_loopback_only(self):
        for good in ("http://127.0.0.1:9000", "http://localhost:9000", "http://[::1]:9000"):
            with self.subTest(origin=good):
                self.assertTrue(skillctl.origin_allowed(good, 9000))
        for bad in (None, "", "*", "null", "https://evil.example",
                    "http://evil.example:9000", "http://192.168.1.5:9000",
                    "http://127.0.0.1:9001"):
            with self.subTest(origin=bad):
                self.assertFalse(skillctl.origin_allowed(bad, 9000))

    def _serve(self, token="TOKEN-abc123"):
        """起一个真实的回环服务。

        刻意**不**给 server 挂任何白名单属性 —— 判定必须由真实监听端口推出来。
        回归用例：曾经靠在 do_serve 里给 server 挂 allowed_origins，漏挂一次就成了
        「谁都不放行」的静默故障；单元测试当时自己也挂上了属性，所以照样全绿。
        """
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        page = Path(tmp) / "page.html"
        page.write_text("<html>const SRV = /*__SERVER__*/null;</html>", encoding="utf-8")
        handler = skillctl.make_handler({"doc": {}, "mtime": 0}, {"agents": []}, token, str(page))
        # 请求日志走 stderr，会把测试输出淹掉；这里只静音测试用的这一份
        handler = type("QuietHandler", (handler,), {"log_message": lambda *a, **k: None})
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        srv.daemon_threads = True
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return srv, srv.server_address[1], token

    def _get(self, port, origin=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        if origin is not None:
            req.add_header("Origin", origin)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.headers, resp.read().decode("utf-8")

    def test_foreign_origin_cannot_read_the_token_page(self):
        srv, port, token = self._serve()
        headers, body = self._get(port, origin="https://evil.example")
        # 页面确实带令牌 —— 所以「读不到」才是这条测试的重点
        self.assertIn(token, body)
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"),
                          "外部来源拿到了跨域读许可，等于把会话令牌交出去")
        self.assertIn("no-store", headers.get("Cache-Control", ""),
                      "带令牌的页面不许被缓存")

    def test_absent_origin_gets_no_cors_grant(self):
        srv, port, _ = self._serve()
        headers, _ = self._get(port)
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))

    def test_loopback_origin_still_works(self):
        srv, port, token = self._serve()
        for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            with self.subTest(origin=origin):
                headers, body = self._get(port, origin=origin)
                self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin)
                self.assertIn(token, body)

    def test_write_still_requires_the_token(self):
        srv, port, _ = self._serve()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/action", method="POST",
            data=json.dumps({"action": "uninstall", "name": "x", "agent": "y",
                             "apply": True}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Skillctl-Token": "wrong"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(caught.exception.code, 403)


# ---------------------------------------------------------- 配置表的自说明

def _documented_keys(spec):
    return {k for k in (spec or {}) if not k.startswith("_")}


class ConfigDocsTests(unittest.TestCase):
    """声明式表的每个键都得有说明。

    同事扩展 agents.json 时只能读这张表（不懂代码），所以「代码在用、表里没写」
    与「表里写了、代码没实现」是同一类缺陷的两面。
    """

    def test_every_agent_key_is_documented(self):
        used = {k for a in AGENTS["agents"] for k in a}
        missing = sorted(used - _documented_keys(AGENTS.get("_agent_spec")))
        self.assertEqual(missing, [], f"_agent_spec 里缺这些键的说明：{missing}")

    def test_every_toggle_key_is_documented(self):
        used = set()

        def walk(spec):
            used.update(k for k in spec if not k.startswith("_"))
            # plugin / fallback 与父声明同构，它们的子键也要一起被说明
            for sub in ("plugin", "fallback"):
                if isinstance(spec.get(sub), dict):
                    walk(spec[sub])

        for agent in AGENTS["agents"]:
            walk(agent.get("toggle") or {})
        missing = sorted(used - _documented_keys(AGENTS.get("_toggle_spec")))
        self.assertEqual(missing, [], f"_toggle_spec 里缺这些键的说明：{missing}")

    def test_every_root_key_is_documented(self):
        used = {k for a in AGENTS["agents"] for r in a["roots"] for k in r}
        missing = sorted(used - _documented_keys(AGENTS.get("_root_spec")))
        self.assertEqual(missing, [], f"_root_spec 里缺这些键的说明：{missing}")

    def test_every_top_level_key_is_documented(self):
        used = {k for k in AGENTS if not k.startswith("_")}
        missing = sorted(used - _documented_keys(AGENTS.get("_top_level_spec")))
        self.assertEqual(missing, [], f"_top_level_spec 里缺这些键的说明：{missing}")

    def test_override_example_keys_are_actually_read(self):
        """overrides.json 的样例里写了的键，代码必须真的读它。

        写了没人读 = 用户照着填、以为生效了，实际静默忽略。
        by_entity 与 by_conflict 两张表的样例都要守 —— 只守一张的话，新加那张表正好会漏。
        """
        for table in ("_example", "_by_conflict_example"):
            for key in OVERRIDES[table]["some-skill"]:
                with self.subTest(example=table, key=key):
                    self.assertRegex(SOURCE, rf'(ov\.get\("{key}"\)|"{key}" in ov)',
                                     f"overrides.json 的 {table} 里有 {key}，但代码从没读过它")


class ConfigHardFailureTests(unittest.TestCase):
    """本 skill 自己的配置表坏了必须响亮失败，不能静默降级。

    用读别人状态文件那种「坏了就当没有」的兜底来读自己的配置，会造出最坏的
    一种失败：rules.json 里多一个逗号 → 空规则表 → 全场 PASS。`check` 的输出
    跟「这台机器真干净」长得一模一样，唯一信号是 FAIL 数突然归零 —— 而那正是
    没人会去怀疑的信号。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(setattr, skillctl, "BASE", skillctl.BASE)
        skillctl.BASE = self.tmp
        skillctl.set_artifact_root(os.path.join(self.tmp, "art"))
        self.addCleanup(skillctl.set_artifact_root, None)
        for name in CONFIG_FILES:
            shutil.copy(SKILL_DIR / name, os.path.join(self.tmp, name))

    def _break(self, name):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as fh:
            fh.write("{ 这不是合法 JSON")

    def test_broken_config_fails_loudly_instead_of_reporting_nothing(self):
        for name in CONFIG_FILES:
            with self.subTest(config=name):
                shutil.copy(SKILL_DIR / name, os.path.join(self.tmp, name))
                self._break(name)
                with self.assertRaises(skillctl.ConfigError) as ctx:
                    skillctl.do_scan(argparse.Namespace(no_html=True))
                self.assertIn(name, str(ctx.exception),
                              f"{name} 坏了却没在报错里点名它")
                shutil.copy(SKILL_DIR / name, os.path.join(self.tmp, name))

    def test_a_missing_config_file_is_not_an_error(self):
        """缺文件不等于坏文件：没这个文件就用内置默认值，别拿它当错误。"""
        self.assertIsNone(skillctl.load_config_json(
            os.path.join(self.tmp, "never-existed.json"), "never-existed"))


# ---------------------------------------------------------- 页面给出的命令

class DashboardCommandTests(unittest.TestCase):
    """页面上的命令必须照抄就能跑。

    曾经把 tool_dir 注入成 skill 根，于是页面上每条可复制命令都是
    `python3 <skill>/skillctl.py …` → can't open file。页面打得开、命令跑不通，
    只断言「常量对」是拦不住的：得真跑一遍 scan、再从生成的页面里把值读出来。
    夹具刻意做成一只假 skill，避免测试去走真实 HOME。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(skillctl.set_artifact_root, None)
        self._orig_base = skillctl.BASE
        skillctl.BASE = self.tmp
        self.addCleanup(setattr, skillctl, "BASE", self._orig_base)
        skillctl.set_artifact_root(os.path.join(self.tmp, "art"))

        root = Path(self.tmp) / "roots"
        (root / "alpha").mkdir(parents=True)
        (root / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Use when exercising the panel.\n---\n\n# Alpha\n",
            encoding="utf-8")
        (Path(self.tmp) / "agents.json").write_text(json.dumps({"agents": [
            {"id": "fake", "label": "Fake",
             "roots": [{"path": str(root), "kind": "user_skills"}]}]}), encoding="utf-8")
        for name in ("rules.json", "overrides.json"):
            shutil.copy(SKILL_DIR / name, Path(self.tmp) / name)
        # 模板是生成页面的源，BASE 一换就得跟着搬
        (Path(self.tmp) / "assets").mkdir()
        shutil.copy(SKILL_DIR / "assets" / "dashboard_template.html",
                    Path(self.tmp) / "assets" / "dashboard_template.html")

    def _scan_and_read_doc(self):
        with contextlib.redirect_stdout(io.StringIO()):
            skillctl.do_scan(argparse.Namespace(no_html=False))
        page = Path(skillctl.artifact_html()).read_text(encoding="utf-8")
        head = "const DOC = "
        i = page.index(head)
        return json.loads(page[i + len(head):page.index("\n", i)].strip().rstrip(";"))

    def test_page_advertises_a_runnable_entry_path(self):
        doc = self._scan_and_read_doc()
        entry = Path(doc["tool_dir"], "skillctl.py")
        self.assertTrue(entry.is_file(),
                        f"页面里的 tool_dir 指不到入口脚本：{doc['tool_dir']}")

    def test_python_interpreter_in_the_page_is_this_one(self):
        doc = self._scan_and_read_doc()
        self.assertTrue(Path(doc["python_bin"]).is_file(), doc["python_bin"])


# ---------------------------------------------------------- 通用代码 vs 本地产物

def _minimal_entity(name):
    """够 do_check 打印一条的最小实体。只为本组测试服务。"""
    return {
        "name": name, "verdict": "pass", "real_path": f"/virtual/{name}",
        "type": "local", "type_evidence": "test", "auto_created": False,
        "entity_agents": ["agenta"], "link_agents": [], "agents": ["agenta"],
        "file_count": 1, "total_bytes": 10, "link_count": 0,
        "description": "fixture", "checks": [], "refs": [],
        "unknown_state_agents": [],
    }


class PlanPackageTests(unittest.TestCase):
    """方案包里的时间戳必须自洽：文件名、脚本里的 TRASH、清单内文说的是同一刻。

    曾经清单印的是快照时间，而文件名用的是当下时间 —— 差着一次 scan 的距离。
    照着清单里的时间去 trash 目录找，永远对不上号。所以这里不比对常量，而是真跑一次
    plan、把生成的 md 打开读。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(skillctl.set_artifact_root, None)
        self._orig_base = skillctl.BASE
        skillctl.BASE = self.tmp
        self.addCleanup(setattr, skillctl, "BASE", self._orig_base)
        self._env = os.environ.pop("SKILL_PANEL_OUT", None)
        if self._env is not None:
            self.addCleanup(os.environ.__setitem__, "SKILL_PANEL_OUT", self._env)

        skillctl.set_artifact_root(os.path.join(self.tmp, "art"))
        root = Path(self.tmp) / "roots"
        root.mkdir()
        (Path(self.tmp) / "agents.json").write_text(json.dumps({"agents": [
            {"id": "fake", "label": "Fake",
             "roots": [{"path": str(root), "kind": "user_skills"}]}]}), encoding="utf-8")
        for name in ("rules.json", "overrides.json"):
            shutil.copy(SKILL_DIR / name, Path(self.tmp) / name)

    # 快照时间刻意做得跟「现在」明显不同，否则时间戳写错了也可能碰巧撞对
    SNAPSHOT_AT = "2020-01-02T03:04:05+08:00"

    def _write_snapshot(self):
        doc = {
            "generated_at": self.SNAPSHOT_AT, "host": "testhost",
            "entities": [], "conflicts": [{
                "name": "twin", "kind": "identical", "count": 2,
                "entities": [{"real_path": "/virtual/a/twin", "agents": ["agenta"]},
                             {"real_path": "/virtual/b/twin", "agents": ["agentb"]}],
                "nature": "duplicate", "liveness": "live", "version_drift": [],
                "prescription": {
                    "grade": "auto", "canonical": "/virtual/a/twin",
                    "canonical_why": "fixture", "needs_diff": False,
                    "rewrite": [{"path": "/virtual/b/twin", "agents": ["agentb"],
                                 "link_count": 0}],
                },
            }], "skipped": [], "agent_stats": [],
        }
        path = Path(skillctl.artifact_json())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")

    def _run_plan(self):
        self._write_snapshot()
        args = argparse.Namespace(names=None, auto_only=False, grades="auto")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(skillctl.do_plan(args), 0)
        md = sorted(Path(skillctl.artifact_root()).glob("plan-*.md"))
        sh = sorted(Path(skillctl.artifact_root()).glob("plan-*.sh"))
        self.assertEqual(len(md), 1, f"应恰好产出一份清单，实际 {[p.name for p in md]}")
        self.assertEqual(len(sh), 1)
        return md[0], sh[0]

    def test_manifest_time_matches_the_filename_stamp(self):
        md, sh = self._run_plan()
        stamp = md.stem[len("plan-"):]
        want = (f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
                f"T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}")
        got = re.search(r"生成时间：(\S+)", md.read_text(encoding="utf-8")).group(1)
        self.assertTrue(got.startswith(want),
                        f"清单写「生成时间：{got}」，文件名却是 {stamp} —— "
                        f"照清单去 trash 找会对不上")

    def test_script_trash_dir_carries_the_same_stamp(self):
        md, sh = self._run_plan()
        stamp = md.stem[len("plan-"):]
        self.assertEqual(sh.stem[len("plan-"):], stamp)
        self.assertIn(f"TRASH=\"{skillctl.trash_root()}/plan-{stamp}\"",
                      sh.read_text(encoding="utf-8"))

    def test_snapshot_time_is_reported_separately(self):
        """快照时间要单独标出来，不能顶替生成时间，也不能悄悄丢掉。"""
        md, _ = self._run_plan()
        text = md.read_text(encoding="utf-8")
        self.assertIn(f"基于快照：{self.SNAPSHOT_AT}", text)
        got = re.search(r"生成时间：(\S+)", text).group(1)
        self.assertNotEqual(got, self.SNAPSHOT_AT,
                            "生成时间又变回快照时间了（差一次 scan，按它找 trash 会对不上）")


class ResolveConflictTests(unittest.TestCase):
    """一键去重：留一份作正本，其余副本换成指向它的快捷方式。

    这是条会动真实目录的写路径，所以每条约束都要有对应用例：干跑一个字节不动、
    落盘后原副本在回收站、台账留痕、重复点不会把正本自己干掉、需人工的档不碰。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(skillctl.set_artifact_root, None)
        self._orig_base = skillctl.BASE
        skillctl.BASE = self.tmp
        self.addCleanup(setattr, skillctl, "BASE", self._orig_base)
        self._env = os.environ.pop("SKILL_PANEL_OUT", None)
        if self._env is not None:
            self.addCleanup(os.environ.__setitem__, "SKILL_PANEL_OUT", self._env)
        skillctl.set_artifact_root(os.path.join(self.tmp, "art"))

        self.canon = Path(self.tmp) / "rootsA" / "dup"
        self.other = Path(self.tmp) / "rootsB" / "dup"
        for d in (self.canon, self.other):
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("---\nname: dup\n---\n\nsame\n", encoding="utf-8")

    def _doc(self, grade="auto", canonical=None, rewrite=None, nature="duplicate"):
        return {"generated_at": "2020-01-01T00:00:00+08:00", "host": "test",
                "entities": [], "skipped": [], "agent_stats": [],
                "conflicts": [{
                    "name": "dup", "kind": "identical", "count": 2,
                    "entities": [{"real_path": str(self.canon), "agents": ["agenta"]},
                                 {"real_path": str(self.other), "agents": ["agentb"]}],
                    "nature": nature, "liveness": "live", "version_drift": [],
                    "prescription": {
                        "grade": grade,
                        "canonical": str(canonical if canonical is not None else self.canon),
                        "canonical_why": "fixture", "needs_diff": False,
                        "rewrite": (rewrite if rewrite is not None else
                                    [{"path": str(self.other), "agents": ["agentb"],
                                      "link_count": 0}]),
                    },
                }]}

    def _run(self, doc=None, dry_run=True, **kw):
        return skillctl.resolve_conflict(doc or self._doc(), None, dry_run=dry_run, **kw)

    def test_dry_run_touches_nothing(self):
        log, ops, groups, skipped, warns = self._run()
        self.assertTrue(ops, "干跑应当给出 ops 计划")
        self.assertEqual(len(groups), 1)
        self.assertFalse(self.other.is_symlink(), "干跑把目录换成软链了")
        self.assertEqual(len(list((self.other).iterdir())), 1, "干跑动了原副本")
        self.assertFalse(os.path.exists(skillctl.trash_root()), "干跑建了回收站")
        self.assertFalse(os.path.exists(skillctl.ledger_path()), "干跑写了台账")
        self.assertEqual([o["kind"] for o in ops], ["move", "symlink"])

    def test_apply_swaps_copy_for_a_link_and_keeps_it_in_trash(self):
        log, ops, groups, skipped, warns = self._run(dry_run=False)
        self.assertTrue(self.other.is_symlink(), "原副本没换成快捷方式")
        self.assertEqual(os.path.realpath(self.other), os.path.realpath(self.canon))
        self.assertTrue((self.other / "SKILL.md").is_file(),
                        "换完之后通过软链读不到内容")
        self.assertTrue(self.canon.is_dir() and not self.canon.is_symlink(),
                        "正本不该被动")
        # 原副本进了回收站，不是被删掉
        trashed = list(Path(skillctl.trash_root()).rglob("dup"))
        self.assertEqual(len(trashed), 1, f"回收站里没有原副本：{trashed}")
        self.assertTrue((trashed[0] / "SKILL.md").is_file())
        # 台账留痕
        led = json.loads(Path(skillctl.ledger_path()).read_text(encoding="utf-8"))
        self.assertEqual([a["action"] for a in led["actions"]], ["resolve-conflict"])
        self.assertEqual(led["actions"][0]["groups"][0]["name"], "dup")

    def test_second_run_is_a_no_op(self):
        self._run(dry_run=False)
        log, ops, groups, skipped, warns = self._run(dry_run=False)
        self.assertFalse(ops, "重复点不该再产生动作")
        self.assertEqual(groups, [])
        self.assertTrue(any("已经是" in s["why"] and "快捷方式" in s["why"]
                            for s in skipped), skipped)
        self.assertTrue(self.canon.is_dir(), "重复执行把正本弄没了")

    def _manual_doc(self, entities, canonical, auto_repairable=False):
        """手搭一份「正文已分叉」的冲突，用来单独验证需人工档的进入条件。"""
        return {"generated_at": "2020-01-01T00:00:00+08:00", "host": "test",
                "entities": [], "skipped": [], "agent_stats": [],
                "conflicts": [{
                    "name": "dup", "kind": "divergent", "count": len(entities),
                    "entities": entities, "nature": "duplicate", "liveness": "live",
                    "version_drift": [],
                    "prescription": {"grade": "manual", "canonical": canonical,
                                     "canonical_why": "fixture", "needs_diff": False,
                                     "auto_repairable": auto_repairable,
                                     "rewrite": []},
                }]}

    @staticmethod
    def _copy(path, agents, exists=True, link_at=(), real=1, links=0):
        return {"real_path": path, "agents": list(agents), "path_exists": exists,
                "link_at": list(link_at), "real_file_count": real, "link_file_count": links}

    def _make_dangling(self, target):
        shutil.rmtree(self.other)
        os.symlink(target, str(self.other))
        return str(self.other)

    def test_a_lone_dangling_copy_is_repaired_without_a_human_pick(self):
        """断链 + 好副本：把链指回正本不涉及任何取舍（后面本来什么都没有），工具该自己修。

        实测本机 ~/.claude/skills/find-skills 就是这种形态 —— 它以前还会被选成正本，
        照那个建议执行等于把好副本换成指向空气的快捷方式。
        """
        gone = str(Path(self.tmp) / "rootsA" / "gone-dup")
        at = self._make_dangling(gone)
        doc = self._manual_doc([self._copy(gone, ["agentb"], exists=False, link_at=[at],
                                           real=0),
                                self._copy(str(self.canon), ["agenta"])],
                               str(self.canon), auto_repairable=True)
        log, ops, groups, skipped, warns = self._run(doc, dry_run=False)
        self.assertEqual([o["kind"] for o in ops], ["unlink", "symlink"], ops)
        self.assertEqual(os.path.realpath(self.other), os.path.realpath(self.canon))
        self.assertEqual(groups[0]["relinked"], [at])
        self.assertEqual(groups[0]["from"], [], "断链修复不该往回收站搬东西")
        # 撤销要明说这一条不还原 —— 假装能还原只会让人以为撤了
        _, _, _, _, undo_warns = skillctl.undo_resolve(doc, dry_run=True)
        self.assertTrue(any("断链修复" in w for w in undo_warns), undo_warns)

    def test_a_dangling_copy_does_not_unlock_real_divergence(self):
        """真分叉的两份 + 一条断链：不能因为「顺带有条断链」就把整组当可自动 ——
        那会把另一份真改动过的正文推进回收站，而留哪份是人的取舍。
        """
        third = Path(self.tmp) / "rootsC" / "dup"
        third.mkdir(parents=True)
        (third / "SKILL.md").write_text("---\nname: dup\n---\n\nother body\n",
                                       encoding="utf-8")
        gone = str(Path(self.tmp) / "rootsA" / "gone-dup")
        at = self._make_dangling(gone)
        doc = self._manual_doc([self._copy(gone, ["pool"], exists=False, link_at=[at],
                                           real=0),
                                self._copy(str(self.canon), ["agenta"]),
                                self._copy(str(third), ["agentb"])],
                               str(self.canon))
        _, ops, _, skipped, _ = self._run(doc)
        self.assertFalse(ops, ops)
        self.assertTrue(any("正文已分叉" in s["why"] for s in skipped), skipped)
        self.assertTrue(third.is_dir(), "需人工的组被动过")

    def test_manual_grade_is_never_touched(self):
        log, ops, groups, skipped, warns = self._run(self._doc(grade="manual"))
        self.assertFalse(ops)
        self.assertFalse(self.other.is_symlink())
        self.assertEqual(skipped[0]["name"], "dup")

    def test_semi_needs_the_explicit_flag(self):
        doc = self._doc(grade="semi")
        _, ops, _, _, _ = self._run(doc)
        self.assertFalse(ops, "半自动档默认不该被处理")
        _, ops2, groups2, _, _ = self._run(doc, allow_semi=True)
        self.assertTrue(ops2 and groups2, "显式 allow_semi 之后应当处理")

    def test_missing_canonical_is_refused_with_a_reason(self):
        doc = self._doc(canonical=Path(self.tmp) / "nope" / "dup")
        log, ops, groups, skipped, warns = self._run(doc)
        self.assertFalse(ops)
        self.assertTrue(any("候选正本" in w for w in warns), warns)

    def test_conflict_whose_copies_are_gone_is_skipped(self):
        shutil.rmtree(self.other)
        log, ops, groups, skipped, warns = self._run()
        self.assertFalse(ops)
        self.assertTrue(any("不存在" in w for w in warns), warns)

    def test_cli_resolve_is_dry_run_without_yes(self):
        """CLI 也走同一条路径：不带 --yes 只预览，报告里要带下次怎么执行。"""
        self._write_snapshot()
        args = argparse.Namespace(names=None, semi=False, yes=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(skillctl.do_resolve(args), 0)
        text = out.getvalue()
        self.assertIn("干跑预览", text)
        self.assertIn("--yes", text)
        self.assertFalse(self.other.is_symlink(), "不带 --yes 就动手了")

    def _write_snapshot(self):
        path = Path(skillctl.artifact_json())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._doc()), encoding="utf-8")
        (Path(self.tmp) / "agents.json").write_text(
            json.dumps({"agents": [{"id": "agenta", "label": "A",
                                    "roots": [{"path": str(Path(self.tmp) / "rootsA"),
                                               "kind": "user_skills"}]}]}),
            encoding="utf-8")
        for name in ("rules.json", "overrides.json"):
            shutil.copy(SKILL_DIR / name, Path(self.tmp) / name)


class ArtifactLayoutTests(unittest.TestCase):
    """通用代码与本地产物必须分家：代码在 skill 目录里，产物在 $HOME/.skill-panel。

    混着放的代价是具体的 —— 市场式安装的 skill 目录可能只读、插件升级整目录替换，
    而快照与仪表盘里含本机路径和命中的凭据原文。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(skillctl.set_artifact_root, None)
        # 跑测人 shell 里的 SKILL_PANEL_OUT 会串味，先摘掉；测完原样放回
        self._env = os.environ.pop("SKILL_PANEL_OUT", None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._env is None:
            os.environ.pop("SKILL_PANEL_OUT", None)
        else:
            os.environ["SKILL_PANEL_OUT"] = self._env

    def test_default_root_is_not_inside_the_skill_dir(self):
        root = skillctl.artifact_root()
        self.assertEqual(root, skillctl.STATE_ROOT)
        self.assertFalse(root == skillctl.BASE or root.startswith(skillctl.BASE + os.sep),
                         f"默认落点落在 skill 目录里: {root}")

    def test_no_product_path_is_built_from_the_skill_dir(self):
        """除了那句「旧产物还在」的提示，代码里不许再有按 BASE 拼产物路径的地方。"""
        offenders = [line.strip() for line in SOURCE.splitlines()
                     if 'BASE, "data"' in line or 'BASE, "skill-panel.html"' in line]
        self.assertEqual(offenders, [], f"产物路径又拼回 skill 目录了: {offenders}")

    def test_env_var_overrides_default(self):
        os.environ["SKILL_PANEL_OUT"] = self.tmp
        self.assertEqual(skillctl.artifact_root(), self.tmp)

    def test_explicit_override_beats_env_var(self):
        os.environ["SKILL_PANEL_OUT"] = os.path.join(self.tmp, "env")
        explicit = os.path.join(self.tmp, "explicit")
        skillctl.set_artifact_root(explicit)
        self.assertEqual(skillctl.artifact_root(), explicit)

    def test_every_artifact_lives_under_one_root(self):
        skillctl.set_artifact_root(self.tmp)
        for path in (skillctl.artifact_json(), skillctl.artifact_html(),
                     skillctl.trash_root(), skillctl.ledger_path()):
            with self.subTest(path=path):
                self.assertTrue(path.startswith(self.tmp + os.sep), path)

    def test_ledger_and_trash_follow_the_root(self):
        """台账与回收站也得跟着走 —— 否则 --out 会把状态悄悄漏回真实 HOME。"""
        skillctl.set_artifact_root(self.tmp)
        skillctl.save_ledger({"version": 1, "actions": [{"action": "disable"}]})
        self.assertTrue((Path(self.tmp) / "ledger.json").is_file())
        self.assertEqual(skillctl.load_ledger()["actions"][0]["action"], "disable")

    def test_render_html_writes_under_the_root(self):
        skillctl.set_artifact_root(self.tmp)
        out = skillctl.render_html({"generated_at": "2026-01-01T00:00:00+08:00",
                                    "entities": []})
        self.assertEqual(out, skillctl.artifact_html())
        self.assertEqual(os.path.dirname(out), self.tmp)
        self.assertTrue(os.path.isfile(out))

    def test_reader_reads_the_configured_root_not_the_skill_dir(self):
        """读者与写者认同一个落点：快照放新落点能读到，放旧落点读不到。"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.addCleanup(setattr, skillctl, "BASE", skillctl.BASE)
        skillctl.BASE = base
        skillctl.set_artifact_root(self.tmp)
        doc = {"generated_at": "2026-01-01T00:00:00+08:00", "host": "test",
               "entities": [_minimal_entity("alpha-report")], "conflicts": [],
               "skipped": [], "agent_stats": []}

        legacy = Path(skillctl.legacy_artifact_paths()[0])
        self.assertTrue(str(legacy).startswith(base), "旧落点得是临时目录，别写进真仓库")
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps(doc), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(skillctl.do_check(argparse.Namespace(name="alpha-report")), 1)
        self.assertIn("还没有扫描产物", err.getvalue())
        self.assertIn(skillctl.artifact_json(), err.getvalue(),
                      "提示里得写明找的是哪个路径，否则落点配错时没法自查")

        path = Path(skillctl.artifact_json())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(skillctl.do_check(argparse.Namespace(name="alpha-report")), 0)
        self.assertIn("alpha-report", out.getvalue())

    def test_out_flag_works_on_both_sides_of_the_subcommand(self):
        """`--out X scan` 与 `scan --out X` 必须等价。

        argparse 解析子命令时在新建命名空间里补默认值再整体盖回父命名空间；
        子命令那份默认值若不是 SUPPRESS，前面的 --out 会被一个 None 抹掉。
        """
        seen = []
        original = skillctl.do_agents
        skillctl.do_agents = lambda args: seen.append(skillctl.artifact_root()) or 0
        self.addCleanup(setattr, skillctl, "do_agents", original)
        for argv in (["agents", "--out", self.tmp], ["--out", self.tmp, "agents"]):
            with self.subTest(argv=argv):
                seen.clear()
                saved = sys.argv
                sys.argv = ["skillctl.py"] + argv
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        code = skillctl.main()
                finally:
                    sys.argv = saved
                    skillctl.set_artifact_root(None)
                self.assertEqual(code, 0)
                self.assertEqual(seen, [self.tmp])

    def test_pretty_path_collapses_home(self):
        self.assertEqual(skillctl.pretty_path(skillctl.HOME + "/x"), "~/x")
        self.assertEqual(skillctl.pretty_path("/tmp/elsewhere"), "/tmp/elsewhere")


if __name__ == "__main__":
    unittest.main(verbosity=2)
