# 羽毛球回合剪辑

日常使用请从 [统一运动工作台](../../apps/football-ai-studio/README.md) 创建“羽毛球”场次，导入、指定目标球员、复核和导出都在同一个页面完成。这个目录保留独立命令行流程。

把固定机位录像整理成可复核的活动候选，确认后导出原片时间码清单供 ChatCut Desktop 建立可编辑时间线；也可生成 MP4 预览。当前识别基于本地画面运动和少量音频信号；候选不等于已确认的完整回合，也不会自动认出指定球员。

```bash
python3 scripts/run.py '/path/to/match.MOV' --serve --open
# 指定人物集锦：
python3 scripts/run.py '/path/to/match.MOV' --mode person --target-description '白衣黄裤' --serve --open
```

独立命令行流程的复核页为 `http://127.0.0.1:8766/review.html`。页面顶部先设定活动或指定人物集锦、衣着特征和回合数 N。候选按原片顺序排列，按评分预选只改变勾选；逐段核对回合起止和目标人物，标记高光、写备注。点击“导出 ChatCut 交接清单”得到包含原片绝对路径与精确时间码的 JSON，在 ChatCut Desktop 导入原片后让 Agent 按清单建立时间线。JSON 不是 ChatCut 原生工程文件。原片不会被覆盖。

如果开头在摆放相机，可加 `--ignore-before 8` 跳过前 8 秒。邻场活动干扰明显时，可加 `--court-roi X Y W H`，四个数分别是目标球场左上角和宽高，占整幅画面的 0–1 比例，例如 `--court-roi 0.1 0.22 0.85 0.72`。正式全程固定录制通常不需要跳过开头。

用户提供的 63.66 秒样片在跳过前 8 秒后得到三个待审候选：8–24、24–40、52–62 秒。是否是完整回合、是否属于白衣黄裤球员的精彩表现，仍以页面人工复核为准。详见 [开发记录](DEVELOPMENT.md)。

ChatCut 交接格式与 Agent 指令见 [运动片段交接说明](../../docs/skills/chatcut-handoff.md)。
