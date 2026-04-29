# circle-content-analyzer

面向 B 站会员购漫展圈三条入口的内容分析 skill。

## 当前状态

这个目录先收敛 skill 协议层：

- 统一触发条件
- 统一 14 类内容类型口径
- 明确 `uv_expose > 100` 的结论过滤规则
- 明确 HTML 上传必须是用户显式授权的 opt-in 行为

这次补丁的重点是把 skill 从“说明和实现漂移”拉回“协议一致、边界清楚”。

## 适用输入

需要三张 Excel：

- `票务商详讨论区圈子内容曝光点击数据-xxxx.xlsx`
- `票务商详讨论区圈子入口进入圈子后，圈子内内容曝光点击数据-xxxx.xlsx`
- `T3圈子入口进入圈子后，圈子内内容曝光点击数据-xxxx.xlsx`

## 分析口径

### 14 个内容类型

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

详细规则见 [references/content_types.md](/Users/raincai/.codex/worktrees/15b7/raincoat/skills/circle-content-analyzer/references/content_types.md)。

### 结论层过滤

- 概览指标可统计全量
- 结论层分析只纳入 `uv_expose > 100` 的内容

## 上传边界

报告默认只生成本地 HTML/JSON。

只有在用户明确要求公网链接或远程分发时，才允许上传 HTML；上传前应明确说明目标地址和结果形式。

## 目录结构

```text
circle-content-analyzer/
├── SKILL.md
├── README.md
├── references/
│   └── content_types.md
└── scripts/
    └── README.md
```

## 后续建议

如果要补回正式运行时，优先恢复一个明确的 `scripts/generate_report.py` 入口，并满足：

- 默认不上传
- 显式 `--upload` 才联网
- 不保留个人绝对路径常量
- 用真实样本做冒烟验证
