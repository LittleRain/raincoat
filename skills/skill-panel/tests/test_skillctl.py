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

    implementation = set(re.findall(r'det == "([a-z_]+)"', SOURCE))

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
    def ent(path, links=0, holders=()):
        return {"real_path": path, "link_count": links, "entity_agents": list(holders),
                "agents": ["a"], "name": "dup"}

    def test_canonical_scoring_prefers_shared_pool_then_editable_copies(self):
        """正本挑选顺序：跨 agent 共享池 > 不在 App 包内（改它不会被升级覆盖）> 实体本体。"""
        home = os.path.expanduser("~")
        shared = self.ent(os.path.join(home, ".agents", "skills", "dup"), links=1)
        plain = self.ent("/tmp/somewhere/dup")
        app = self.ent("/Applications/SomeApp.app/Contents/skills/dup")
        held_app = self.ent("/Applications/SomeApp.app/Contents/skills/dup", holders=["x"])
        scores = [skillctl._score_canonical(x)[0] for x in (shared, plain, app, held_app)]
        self.assertGreater(scores[0], scores[1], "共享池应压过普通副本")
        self.assertGreater(scores[1], scores[2], "可改的副本应压过 App 包内的")
        self.assertGreater(scores[3], scores[2], "有 agent 直接持有的应压过无来源的")

    def test_more_symlink_references_score_higher(self):
        plain = self.ent("/tmp/somewhere/dup")
        linked = self.ent("/tmp/somewhere/dup", links=3)
        self.assertGreater(skillctl._score_canonical(linked)[0],
                           skillctl._score_canonical(plain)[0])

    def test_scoring_reason_is_always_non_empty(self):
        for label in ("共享池", "App 包内", "普通副本"):
            with self.subTest(label=label):
                path = {"共享池": os.path.join(os.path.expanduser("~"), ".agents", "skills", "d"),
                        "App 包内": "/Applications/A.app/skills/d",
                        "普通副本": "/tmp/d"}[label]
                self.assertTrue(skillctl._score_canonical(self.ent(path))[1])

    def test_prescription_grade_matrix(self):
        ents = [self.ent("/tmp/a", links=2), self.ent("/tmp/b")]
        expected = {"identical": "auto", "meta-only": "auto",
                    "same-body-diff-files": "semi", "divergent": "manual"}
        for kind, grade in expected.items():
            with self.subTest(kind=kind):
                result = skillctl.prescribe(kind, "duplicate", "active", ents)
                self.assertEqual(result["grade"], grade)
                self.assertTrue(result["rewrite"])
                self.assertEqual(result["needs_diff"], grade in ("semi", "manual"))

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
        # 只缺扫描快照，配置照旧 —— 否则先撞上「agents.json 缺失」，测不到这条。
        for name in CONFIG_FILES:
            shutil.copy(SKILL_DIR / name, Path(self._tmp) / name)
        self.assertFalse((Path(self._tmp) / "data" / "skills.json").exists())

    def tearDown(self):
        skillctl.BASE = self._orig_base
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
        """
        for key in OVERRIDES["_example"]["some-skill"]:
            with self.subTest(key=key):
                self.assertRegex(SOURCE, rf'(ov\.get\("{key}"\)|"{key}" in ov)',
                                 f"overrides.json 的样例里有 {key}，但代码从没读过它")


if __name__ == "__main__":
    unittest.main(verbosity=2)
