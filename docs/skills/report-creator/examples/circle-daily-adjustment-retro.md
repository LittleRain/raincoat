# 圈子业务日报 Skill 定向调整复盘（2026-04-01）

## 背景

首版 `report-circle-daily` 已能生成 HTML，但业务评审反馈“结论偏浅、可执行性不足”。
在补充需求后，进行了第二轮定向调整，并出现一次运行时报错。

关联文档：
- 源需求：[圈子业务日报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务日报需求.md)
- 生成记录：[circle-daily-generation-run.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/examples/circle-daily-generation-run.md)
- 下游 skill：[report-circle-daily](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily)

## 偏差与坑位

### 1. 结果“看起来完整”，但结论不够深

表现：
- 结论以描述性话术为主，缺少可复核数字
- 缺“总览层”信息，业务方难快速判断重点

根因归属：
- 下游 skill 脚本层（分析逻辑深度不够）
- HTML 合同层（未明确“结论必须带指标证据”）

### 2. 输出结构与更新后的需求不完全一致

表现：
- 需求要求先出“总览表”，首版没有
- 内容 Top10 需求为“按曝光排序”，首版以点击排序为主
- 内容表缺少部分字段（副标题、发布时间、链接）

根因归属：
- 标准化 spec 摘要与资产合同未及时同步到最新需求
- 下游 skill 的结构模板未收敛到“强约束字段”

### 3. 运行时稳定性问题（真实报错）

报错：
- `TypeError: sequence item 0: expected str instance, float found`
- 触发点：高效率内容标题拼接时，`title` 含空值/非字符串

根因归属：
- 下游 skill 脚本鲁棒性不足（字段空值与类型防护不完整）

## 本次定向调整动作

### A. 结构层调整（对齐需求）

- 固定栏目调整为：
  1) 总览
  2) 绘画圈内容分析
  3) 模型圈内容分析
  4) 漫展圈双路径内容分析
  5) 漫展项目转化分析
- 明确内容 Top10 按曝光排序
- 内容表强制字段：标题、副标题、发布时间、曝光、点击、CTR、链接

### B. 结论层调整（提升深度）

- 所有栏目结论改为“结论 + 指标证据”格式
- 增加场景级对比：T3 vs 票务商详 CTR、集中度、主导类型、项目重叠
- 项目转化增加漏斗拆解：曝光承接率、点击承接率、UV CTR

### C. 稳定性调整（防 crash）

- 对标题字段统一做：`dropna -> astype(str) -> strip -> 过滤 nan`
- 无可用标题时输出降级结论，禁止抛异常中断

### D. 验证与回归

- 编译检查：`python3 -m py_compile` 通过
- 自动化测试：`tooling/tests/report-circle-daily.sh` 通过
- 测试断言补充：总览区、链接字段、漏斗承接率关键字

## 可复用经验（下一次直接套用）

1. 当业务反馈“结论浅”时，不要先改文案，先补“指标证据结构”。
2. 输出合同要把“结论深度”写成硬约束，而不是软建议。
3. 任何参与文案拼接的字段（title/item/source）都必须先做类型清洗。
4. 双路径/多口径场景必须在合同里明确“禁止混算”。
5. 回归测试关键字应覆盖“结构字段 + 关键指标 + 链接规则”。

## 建议沉淀到 create-report 的通用规则

- 在 `validation` 增加“结论证据化检查”：至少 2-3 条结论含可追溯指标
- 在 `generation` 阶段默认生成“字段鲁棒性防护模板”（空值/类型/缺列）
- 在调整回归样例中，把“运行时异常”作为必须记录项
