# Rain Badminton Cut 开发交接文档

> 面向后续 Agent 的开发说明。本文记录截至 2026-09-07 的设计、实现状态、测试方式和未完成工作。

## 1. 项目目标

`rain-badminton-cut` 用于把横屏羽毛球比赛视频自动整理为精彩回合合集：

```text
输入视频
  → 本地视频探测与特征提取
  → 候选完整回合识别
  → 精彩程度评分
  → 生成精选/标准/完整版方案
  → HTML 页面人工确认和微调
  → FFmpeg 输出最终合集
```

最重要的产品约束是“回合完整性”优先于剪辑激进程度：宁可多保留几秒，也不要从杀球中间开始或在得分前结束。

## 2. 当前目录位置

当前 Skill 是独立目录，还没有重新集成到已删除的 `raincoat` 仓库：

```text
/Users/claw/Documents/Codex/2026-09-04/skill-grillme/rain-badminton-cut
```

现有文件：

```text
SKILL.md                         Agent 使用说明和工作流约束
config.example.yaml              配置模板
agents/openai.yaml               UI 元数据
scripts/preflight.py             FFmpeg/mmx 环境预检
scripts/analyze_video.py         本地运动量/音频能量候选生成器
scripts/analyze_with_mmx.py      对关键帧调用 mmx vision
scripts/generate_review_html.py  生成 HTML 复核页
scripts/render_highlights.py     校验 edits.json 并合并视频
scripts/review_server.py         本机复核页服务与确认后渲染
references/provider-interface.md 分析后端 JSON 契约
references/scoring-model.md      评分设计
references/review-schema.md      HTML 编辑结果格式
```

## 3. 已实现状态

### 已完成

- Skill frontmatter、自动触发描述和基本工作流。
- 可配置分析后端概念：`local-heuristic`、`minimax-cli`、`custom-command`。
- FFmpeg/FFprobe 预检。
- `mmx-cli` 状态、登录和额度预检。
- 基于低分辨率画面运动量和音频能量生成候选；信号不足时退回保守重叠窗口。
- `clips.json` 候选结构。
- HTML 页面生成。
- HTML 中候选片段的保留/删除和开始/结束时间编辑，以及本机服务模式下的确认渲染按钮。
- 导出 `edits.json`。
- 使用 FFmpeg 按编辑结果生成 `highlights.mp4`。
- 未确认的 `edits.json` 会被渲染脚本拒绝。
- MiniMax 视觉分析的独立关键帧调用脚本。
- `scripts/run.py` 一键入口：创建独立复核目录、运行预检、生成候选和 HTML 页面。
- `scripts/review_server.py` 仅在 `127.0.0.1` 提供复核页面服务；页面确认后保存 `edits.json` 并调用渲染器。
- Skill 元数据校验通过。

### 已验证

使用 FFmpeg 生成 12 秒测试视频后，已跑通：

```text
测试视频 → clips.json → review.html → edits.json → highlights.mp4
```

FFmpeg、FFprobe 和本机 `mmx-cli 1.0.12` 均可用。

## 4. 当前真实能力边界

当前版本还不是生产级的自动高光识别器，必须明确以下限制：

1. `analyze_video.py` 以全局画面运动量和音频能量推断活跃区间；它并不真正识别发球、击球、死球或比分变化，因此边界必须人工复核。
2. 候选评分使用本地时长、运动、音频和运动变化信号；“估算击球数”“攻防转换”只是启发式代理，不能当作实测结果。
3. `analyze_with_mmx.py` 可以逐张图片调用 `mmx vision describe`，但还没有自动接入候选合并和评分流程。
4. 当前 HTML 是最小复核页，已有时间范围和保留开关，但精选/标准/完整版、评分权重滑块、目标文件大小估算尚未完整实现。
5. `--serve` 模式通过仅限 `127.0.0.1` 的本机服务提供复核页，并在确认后渲染。不开服务时，HTML 仍可直接打开和导出 `edits.json`。输出目录使用源视频符号链接，避免复制或覆盖原视频。
6. 尚未支持真正的单打/双打球员检测、手持镜头稳定性判断、遮挡判断和回合完整性置信度计算。

因此，当前版本适合验证“编辑页和渲染链路”，不应宣称已经能准确自动挑出精彩回合。

## 5. 配置约定

参考 `config.example.yaml`。核心配置分四组：

### analyzer

```yaml
analyzer:
  provider: minimax-cli
  command: mmx
  vision_command: "mmx vision describe"
```

Token Plan 通过本机 `mmx-cli` 使用，不在项目中保存 API Key。当前已确认的视觉接口接收图片路径/URL或 file ID，不应把 `mmx video generate` 当成视频分析接口。

### rally

```yaml
rally:
  pre_roll_seconds: 4
  post_roll_seconds: 6
  candidate_window_seconds: 30
  candidate_step_seconds: 24
  completeness_threshold: 0.80
```

`pre_roll_seconds` 和 `post_roll_seconds` 是完整性安全边界，自动算法不得无提示地把它们缩短。

### scoring

评分信号应归一化到 0–1，最终使用：

```text
score = 100 × Σ(weight_i × signal_i)
```

建议的信号包括：长回合、估算击球数、移动强度、攻防转换、网前球和音频能量。

### output

默认保留原始分辨率和帧率。未来设置 `max_file_size_mb` 后，HTML 页面应在生成前展示分辨率、码率、时长和预估大小的权衡。

## 6. 当前手动测试

```bash
cd /Users/claw/Documents/raincoat/skills/rain-badminton-cut
python3 scripts/preflight.py
python3 scripts/analyze_video.py /path/to/match.mp4 --out clips.json
python3 scripts/generate_review_html.py clips.json --out review.html
open review.html
```

在页面中导出 `edits.json` 后：

```bash
python3 scripts/render_highlights.py edits.json --out highlights.mp4
```

测试 MiniMax 关键帧分析：

```bash
ffmpeg -i /path/to/match.mp4 \
  -vf "fps=1/2,scale=960:-1" \
  frames-%03d.jpg

python3 scripts/analyze_with_mmx.py \
  frames-001.jpg frames-002.jpg \
  --out mmx-analysis.json
```

## 7. 推荐开发顺序

### P0：一键可测试入口（已完成）

`scripts/run.py` 负责：

1. 校验输入路径。
2. 创建独立输出目录。
3. 调用 `preflight.py`。
4. 调用候选分析器。
5. 生成 HTML。
6. 使用 `--open` 打开 HTML，默认打印打开路径。
7. 在用户确认后调用渲染器。

### P0：HTML 本地预览与确认渲染（已完成）

输出目录创建：

```text
review/
  review.html
  source.<原始扩展名>
```

`--serve` 使用本机服务加载该目录，并接收已确认的编辑数据。后续可为每个候选生成低码率预览片段，降低长视频的浏览器加载成本。

### P1：实现本地回合候选检测

建议不依赖 OpenCV 起步，先使用 FFmpeg：

- `scdet` 或 scene metadata：检测镜头变化。
- `silencedetect` / 音频能量：检测死球和观众反应。
- 定时抽帧：生成关键帧。
- 候选片段前后加安全边界。

之后再引入姿态或球员检测模型。固定机位和手持机位应使用不同阈值。

### P1：接通 MiniMax 视觉结果

`analyze_with_mmx.py` 应升级为：

1. 为每个候选抽取代表帧。
2. 批量调用 `mmx vision describe`。
3. 要求返回严格 JSON。
4. 解析并校验结果。
5. 把信号和理由合并回 `clips.json`。
6. 失败时保留本地候选，不伪造模型结果。

### P1：实现方案选择和评分控件

HTML 需要增加：

- 精选版、标准版、完整版下拉选择。
- 评分因素滑块。
- 最大文件大小输入。
- 分辨率/码率选择。
- 预计总时长和文件大小。
- 低完整性置信度提示。

### P2：真实视频回归测试

至少准备四种样本：

- 固定机位单打。
- 固定机位双打。
- 手持单打。
- 手持双打。

每个样本人工标注回合开始、结束和精彩等级，用来验证：

- 回合是否被截断。
- 是否漏掉发球和死球。
- 精彩排序是否合理。
- 生成的视频是否可播放。

## 8. Agent 开发规则

- 先读 `SKILL.md` 和本文件，再修改脚本。
- 不要把 MiniMax Token 或 API Key 写入代码、配置或日志。
- 不要覆盖原始视频。
- 不要把模型输出直接拼进 shell 命令。
- 时间戳必须经过范围、NaN、重叠和最小长度校验。
- 修改后至少运行 `python3 -m py_compile scripts/*.py`。
- 修改渲染链路后，使用短测试视频跑完整闭环。
- 新增行为时同步更新本文件的“当前真实能力边界”和测试命令。

## 9. 完成定义

当以下命令可以在一条命令中完成候选生成、HTML 打开，并在页面确认后输出合集时，达到 MVP：

```bash
python3 scripts/run.py /path/to/match.mp4 --serve --open
```

当用户调整 HTML 后可以直接点击确认生成合集，并且四种真实拍摄样本的回合边界通过人工验收时，才可以称为第一版可用。
