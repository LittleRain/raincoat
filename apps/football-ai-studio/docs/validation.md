# P0 实际验证 · 2026-10-14

分支：`codex/football-ai-studio-p0`。平台：macOS arm64，Python 3.12.14（独立 .venv），Node 22.16.0，本机真实 FFmpeg/ffprobe。访问：http://127.0.0.1:8765。

## 自动测试

工作目录 `/Users/claw/Documents/raincoat/apps/football-ai-studio`：

```bash
.venv/bin/python -m pytest tests -q
```

实际结果：**9 passed, 1 warning in 22.52s**。警告为第三方 Starlette TestClient 使用 anyio BlockingPortal 弃用别名，未造成测试失败。

覆盖：

1. 场次创建、读、改、软删除，SQLite 重开后保留数据。
2. 真实合成视频上传，ffprobe 时长/尺寸/fps，FFmpeg H.264 代理与 JPEG 缩略图，HTTP Range 206，拒绝访问原片接口。
3. 根目录限制、符号链接越界、目录导入、路径去重，删除场次不删原片。
4. 排队取消与重试、running 状态重启恢复，真实损坏文件失败，修复文件后重试成功。
5. 空文件、错误扩展名、上传大小限制与临时文件清理，Host/Origin 校验。
6. 单 worker 文件锁拒绝第二 worker。
7. 运行中的真实子进程取消，正常停止后重新排队。为限制测试时长，此项用可终止的 sleep 子进程替代长转码，不生成任何分析结果。
8. 一秒合成 3840×2160 与竖屏视频，真实代理生成、尺寸边界与纵横比验证。
9. SIGKILL 模拟 worker 所属进程崩溃，监督器检测管道 EOF 并终止实际子进程。

## 构建与启动

```bash
cd frontend && npm run build
cd .. && ./start.sh
```

实际构建：28 modules，JS 198.84 kB（gzip 63.26 kB），CSS 11.56 kB（gzip 3.70 kB）；成功。`start.sh` 完整执行依赖安装、前端构建、加载 .env 与 API/worker 启动；成功。沙箱默认禁止本地端口绑定，使用已授权的升级执行后服务监听 **127.0.0.1:8765**，未开放 LAN。

```bash
python3 -m compileall -q backend tests
bash -n start.sh
git diff --check
```

语法及差异检查通过（compileall 首次从仓库根使用完整应用路径）。

## 浏览器实际交互

使用 ego-browser，同一 TaskSpace 56（测试结束保留工作台页面）：

- 创建训练场次、改名为「P0 示例 · 合成素材」：通过。
- 选择其他相机、用文件输入上传 3,234,159 字节合成测试图案视频：通过。
- 等待真实预处理显示就绪，元数据 0:04 / 1280×720 / 24 fps：通过。
- 点击卡片播放代理：videoDuration=4.017007，videoWidth=1280，videoHeight=720，currentTime=0.396128，paused=false，URL 为 `/api/media/<id>/proxy`：通过。
- 注册批准根目录的已有视频，不复制原片：通过。
- 再次注册同路径，显示跳过 1 个重复文件：通过。
- 注册 `/private/tmp`，显示路径必须位于批准根目录：通过。
- 注册刻意损坏的 `invalid-demo.mov`，真实 ffprobe 报 moov atom not found；点击重试后 attempts=2，仍显示失败，不冒充成功：通过。
- 新建临时场次并确认删除，列表移除：通过。
- 实际 SIGTERM 停止服务，再执行 `./start.sh` 重启；刷新页面后 3 张素材卡片、2 个成功和1个真实失败仍保留。重启后代理 duration=4.017007，正常加载：通过。
- 重启后 `/api/health` 返回 status=ok、worker_alive=true、ffmpeg=true、ffprobe=true、analysis_available=false、schema_version=1。

### 本次环境问题

初次自动化浏览器读取 Documents 下文件时，File 对象存在但 arrayBuffer 读取超时，服务端未收到上传。复制到 `/private/tmp`、刷新同一页面后，浏览器上传完整通过。本地路径注册原 Documents 文件也通过。可能是 macOS 浏览器文件访问权限；尚未确认根因。普通用户可通过系统文件选择器授予权限，或使用批准目录注册而不上传。此失败未计为通过。

ego-browser CDP 截图接口两次超时，没有获得截图；DOM 交互与实际视频播放验证完成。少数自动化滚动点击出现 stale ref / pointer interception，重新观察页面后点击成功；通过 elementFromPoint 验证播放按钮位于实际点击层。

首次依赖安装因沙箱网络/源未返回依赖而失败，最终通过授权下载安装及 Python 3.12 + PyPI 镜像完成。安装只进入应用 venv 与 frontend/node_modules。npm 缓存移到 data/npm-cache，启动不依赖全局缓存权限。

## 文件变更

- `backend/app.py`：API、流式上传、目录注册、健康、同源限制、代理播放。
- `backend/core.py`、`backend/schema.sql`：SQLite 持久化、版本 1 初始化迁移、路径校验。
- `backend/worker.py`、`backend/supervisor.py`、`backend/__init__.py`：单 worker、真实视频处理、进度、取消/重试/恢复、子进程回收。
- `frontend/src/main.jsx`、`frontend/src/style.css`：React 中文可交互工作台。
- `frontend/index.html`、`frontend/vite.config.js`、`frontend/package.json`、`frontend/package-lock.json`：Vite/React/Tailwind 构建与依赖锁定。
- `requirements.txt`、`.env.example`、`.gitignore`、`start.sh`：后端依赖、配置、启动与本地数据忽略。
- `tests/test_studio.py`、`tests/make_fixture.sh`：自动测试与合成视频工具。
- `README.md`、`docs/provider-interface.md`、`docs/examples.json`、本报告：说明、后续接口设计及示例。
- 仓库根 `README.md`：应用入口；`task_plan.md`、`findings.md`、`progress.md`：实施记录。

虚拟环境、视频、SQLite、转码输出、npm 缓存、node_modules、dist 和 .env 均不进入 Git。

## 遗留与验收边界

未提供真实足球录像，未验证 40 分钟 4K + 多个 iPhone 素材的吞吐/内存峰值/兼容性。短合成 4K 测试不能替代长真实素材验收。HDR/Dolby Vision 色彩未专门处理；无自动磁盘清理；上传中断不续传，重启转码从头恢复。P1/P2/P3 均未开发，真实 AI 识别准确率未验证；无模拟分析结果、无云端视频传输、无发布。
