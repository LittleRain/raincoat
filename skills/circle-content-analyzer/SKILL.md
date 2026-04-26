---
name: circle-content-analyzer
description: Use when analyzing B站会员购漫展圈三张曝光点击 Excel（票务商详讨论区、票务商详进入圈子、T3 入口进入圈子），用户要求识别内容类型、比较内容偏好、做历史趋势对比，或生成 HTML/JSON 分析报告时。
triggers:
  - B站漫展圈内容分析
  - 票务商详讨论区
  - 圈子入口进入圈子后
  - T3入口进入圈子
  - 漫展内容偏好分析
  - 三张Excel内容分析
  - 圈子内容CTR分析
---

# Circle Content Analyzer

## 目的

分析 B 站会员购漫展圈三条入口的内容曝光点击表现，统一内容类型口径，并输出可复查的分析结论。

这个 skill 解决的是一个稳定任务：给定三张固定来源的 Excel，产出结构化分析与对比结论。它不是通用报表助手，也不是让 agent 临时发明内容分类口径的地方。

## 何时使用

- 用户已经提供或即将提供以下三张 Excel：
  - `票务商详讨论区圈子内容曝光点击数据-xxxx.xlsx`
  - `票务商详讨论区圈子入口进入圈子后，圈子内内容曝光点击数据-xxxx.xlsx`
  - `T3圈子入口进入圈子后，圈子内内容曝光点击数据-xxxx.xlsx`
- 用户要求分析内容偏好、高点击/低点击内容、类型分布或趋势变化
- 用户需要 HTML 报告、JSON 结果，或要把本期和上一期结果做对比

## 不适用

- 只有一张表或两张表，且用户没有接受降级分析
- 任务是通用日报/周报生成，而不是三条漫展圈入口的内容分析
- 任务重点是修正分类口径本身，但没有提供错判样例或业务规则更新

## 输入合同

### 三张表对应关系

| 路径 | 文件名关键词 | 说明 |
| --- | --- | --- |
| 票务商详讨论区 | `票务商详讨论区圈子内容曝光点击数据` | 票务商详页讨论区中的圈子内容曝光点击情况 |
| 票务商详进入圈子 | `圈子入口进入圈子后` 且不含 `T3` | 从票务商详页圈子入口进入圈子后的内容曝光点击情况 |
| T3入口进入圈子 | `T3` 且 `圈子入口进入圈子后` | 从 T3 入口进入圈子后的内容曝光点击情况 |

### 关键字段

常见字段：

- `log_date`
- `content_id`
- `url`
- `title`
- `content_text`
- `item_name`
- `start_time`
- `uv_expose`
- `uv_click`
- `uv_ctr`
- `pv_ctr`

表 2、表 3 额外常见：

- `fliter_text` 或 `filter_text`

## 核心规则

### 结论置信度

- 概览指标可基于全量内容统计
- 结论层分析只纳入 `uv_expose > 100` 的内容
- 喜欢/不喜欢内容、类型分布、代表案例、维度表现都必须遵守这个过滤条件

### 内容类型口径

当前统一为 14 类：

1. 吐槽体验
2. 找搭子
3. 约妆约拍
4. 官方情报
5. 无料交换
6. 集邮返图
7. 自由行
8. 疑问解答
9. coser晒图
10. 票务信息
11. 场地信息
12. 现场报道
13. 经验分享
14. 其他

详细边界、优先级与错判修正规则见 [references/content_types.md](/Users/raincai/.codex/worktrees/15b7/raincoat/skills/circle-content-analyzer/references/content_types.md)。

### 路径视角

- 票务路径优先从信息型内容理解点击：`官方情报`、`票务信息`、`疑问解答`、`经验分享`、`场地信息`
- T3 路径优先从视觉吸引力理解点击：`coser晒图`、`现场报道`、`集邮返图`

## 工作流

1. 确认三张表是否齐全；如果不齐全，先说明缺口，不直接给最终结论。
2. 用 `xlsx` 或 pandas 对三张表做结构抽样：
   - 行数是否正常
   - 列名是否齐全
   - `title` / `content_text` 是否有可用样例
   - `start_time` / `log_date` 是否混型
   - 表 2、表 3 是否存在 `fliter_text` 或 `filter_text`
3. 按 [references/content_types.md](/Users/raincai/.codex/worktrees/15b7/raincoat/skills/circle-content-analyzer/references/content_types.md) 的优先级解释分类结果，不要临时发明新大类。
4. 输出时区分：
   - 全量概览
   - `uv_expose > 100` 的结论层分析
   - 如有历史基线，则做本期 vs 上期对比
5. 只有在用户明确要求公网链接或远程分发时，才允许上传 HTML；默认保留本地文件。

## 上传与安全边界

- 默认行为应为本地生成 HTML/JSON，不联网上传
- 如果需要上传，必须先告知：
  - 将上传什么
  - 上传到哪里
  - 上传后得到什么链接
- 用户未明确同意时，不要把报告内容 POST 到外部 API

## 资源地图

- [references/content_types.md](/Users/raincai/.codex/worktrees/15b7/raincoat/skills/circle-content-analyzer/references/content_types.md)：14 类内容类型定义、边界、优先级和错判修正
- `scripts/`：正式脚本入口应放在这里；如果运行时未随包提供，应明确说明缺失实现，而不是伪造结果

## 验证

如果修改或补齐运行时代码，至少验证：

1. `python3 -m py_compile scripts/*.py`
2. 用真实三张 Excel 跑一次完整生成
3. 检查 HTML/JSON 是否生成
4. 检查结论层是否明确体现 `uv_expose > 100`
5. 如果做了历史对比，检查对比模块是否真实引用上一期数据

## 常见坑

- 不要把 `活动预告`、`周边情报` 拆回独立分类；它们并入 `官方情报`
- 不要把 `拍肩集邮` 判回 `集邮返图`；它归 `自由行`
- 不要让 `uv_expose <= 100` 的内容进入结论层表格或代表案例
- 不要把 description 写成长工作流摘要；description 只做触发索引
- 不要引用不存在的 `assets/` 资源
