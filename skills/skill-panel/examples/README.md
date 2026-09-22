# Examples

三张表都可以只改数据、不改代码。这里是最常见的两个改法。

## 1. 把一个项目级 skills 目录纳入扫描

项目级 skill 随 git 仓库走，天然跨 agent 可见，所以默认**不**纳入（纳进来同名撞车会明显变多）。确实需要时，往 `agents.json` 的 `agents` 里加一条 root 即可，见 [`agents.project-level.json`](agents.project-level.json)。

## 2. 豁免一个被误判的 skill

自动判定不可能全对。规则没错、但某个 skill 就是特例时，用 `overrides.json` 的 `by_entity` 精确纠正，见 [`overrides.sample.json`](overrides.sample.json)。改完重跑 `scan` 即生效。

全局噪声（例如成批套壳导致的 `name-dir-mismatch`）应该关规则而不是逐个豁免 —— 那属于 `rules.json` 的 `enabled` 字段，说明见 [`../references/validation-rules.md`](../references/validation-rules.md)。

## 3. 调阈值

体量提示的阈值在 `rules.json` 的 `thresholds` 里：`oversize_text_bytes`（默认 204800）、`short_description_chars`（默认 30）、`evidence_max_per_rule`（默认 5）、`text_read_budget_bytes`（默认 400000）。报表类重资产项目常常超过 200 KB，把 `oversize-text` 的 `enabled` 关掉比调大阈值更清楚。
