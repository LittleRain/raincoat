# 校验规则表

规则与阈值都在 `rules.json`，改规则不用改代码 —— 但 `detector` 必须是 `scripts/skillctl.py` 里已实现的检测器名，写错会直接报错而不是静默失效。

## 阈值

| 键 | 默认 | 含义 |
|---|---|---|
| `oversize_text_bytes` | 204800 | 单个 skill 的文本总体积超过 200 KB 触发 `oversize-text` |
| `short_description_chars` | 30 | `description` 短于 30 字符触发 `short-description` |
| `evidence_max_per_rule` | 5 | 每条规则最多保留几条证据，防止单条规则刷屏 |
| `text_read_budget_bytes` | 400000 | 单文件读取上限；超过就不再读全文，只做存在性判断 |

## 两级

- **FAIL** —— 阻塞跨 agent 迁移：换一个 agent 就读不到、跑不通，或者把凭据带出去。
- **WARN** —— 质量与健壮性提示，不阻塞迁移。

每条结论都带 `文件:行号` 证据。

## FAIL 规则

### 结构性

| id | 判什么 |
|---|---|
| `missing-skill-md` | 目录里没有 `SKILL.md`，任何 agent 都读不到它 |
| `empty-dir` | 目录里一个文件都没有，只剩空壳 |
| `missing-frontmatter` | `SKILL.md` 开头没有 YAML frontmatter，元数据无法解析 |
| `missing-name` | frontmatter 缺 `name`，skill 可能无法被正确索引 |
| `missing-description` | frontmatter 缺 `description`，agent 无法判断何时该调用它 |
| `broken-symlink` | 软链指向的目标已不存在 |
| `broken-script-ref` | 文档引用了 `scripts/` 下的某个文件但磁盘上没有，迁移过去会直接报错 |
| `plugin-root-skill-md` | `SKILL.md` 直接放在插件根、没有 `skills/` 子目录。Bitto 的插件装载校验会拒绝该插件（实测 `plugins/rain-meeting-summary` 装载失败）。正确形态是 `skills/<name>/SKILL.md` |

### 可移植性

| id | 判什么 |
|---|---|
| `secret-literal` | 检出疑似 `token` / `secret` / `api_key` 字面量。迁到别的 agent 等于把凭据复制一份，且极易随 skill 外流 |
| `foreign-abs-path` | 写死的是**非本机用户**的绝对路径，本机根本不存在，迁到任何 agent 都跑不通 |

`secret-literal` 的检出模式与被允许的写法：

| | 内容 |
|---|---|
| 检出 | `sk-…`、`ghp_…`、`github_pat_…`、`AKIA…`、`AIza…`，以及 `token` / `secret` / `password` / `api_key` / `access_key` 后跟 16 位以上字面量赋值 |
| 允许 | `${ENV_VAR}` 与 `<PLACEHOLDER>` 形态；`os.environ` / `getenv` / `settings.` / `config[` / `cfg[` 读取；以及 `your_*` / `changeme` / `xxx` / `fake` / `dummy` / `sample` / `placeholder` / `redacted` / `example` 这类显式占位词 |

## WARN 规则

| id | 判什么 | 为什么只算提示 |
|---|---|---|
| `local-abs-path` | 写死本机 home 的绝对路径 | 同机同用户可用，只是换机/换用户即失效 |
| `oversize-text` | 文本体积超过 `oversize_text_bytes` | 体积大不等于差。业务重资产项目（报表、数据产物）常常很大 |
| `short-description` | `description` 短于 `short_description_chars` | 实测区分度低，主要靠块标量解析修好之后才变干净 |
| `missing-plugin-json` | `plugins/` 载体缺 `plugin.json` 清单 | 只在 Bitto 这类以 plugins 为载体的 agent 上影响识别 |
| `name-dir-mismatch` | frontmatter `name` 与父目录名不一致 | 技能仍可加载，只是每次装载带告警。**成批的「目录名 = 前缀 + name」属于上游统一加前缀，不是缺陷** |
| `symlink-target-unknown` | 源实体被别的 agent 软链引用，但目标 agent 是否支持软链未经验证（`scope: install`） | 不在逐实体校验里跑，只在生成安装指令时出现，指令会自动回退成 `cp -R` |

`scope: install` 的规则不走逐实体校验，而是由安装链路读取：`build_install_text` 只在目标 agent 的 `supports_symlink` 为 `null` 时才追加这条规则的 `desc` 作为提示。所以改它的文案不用改代码，但**改 id 会同时改代码里的引用**（`skillctl.py` 里按 id 取名，写成下划线就取不到了）。

## 两个纠正入口，别用错

- **`rules.json` 的 `enabled`** —— 全局关掉一条规则。适合噪声型的规则：

  ```json
  { "id": "name-dir-mismatch", "enabled": false }
  ```

- **`overrides.json` 的 `by_entity`** —— 只针对某一个 skill 纠正。适合「规则没错，但这个 skill 是特例」，可以改类型、改备注，或用 `ignore_rules` 精确豁免某条规则。

  改完不用做别的，重跑 `scan` 即生效。
