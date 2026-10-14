# Football AI Studio · P0

本地足球训练视频工作台。React + Vite + Tailwind，FastAPI + SQLite，单 worker 调用真实 FFmpeg/ffprobe。**目前只有素材管理和预处理，没有 AI 识别、集锦分析或成片导出。** 原文件始终保留在本机，不调用云服务、不自动发布。

## macOS 启动

需要 Python 3.11+、Node.js 20.19+ / 22.12+、FFmpeg（含 libx264）：

```bash
brew install python node ffmpeg
cd /Users/claw/Documents/raincoat/apps/football-ai-studio
./start.sh
```

启动脚本建立 `.venv`、安装锁定的直接 Python 依赖和 npm 锁文件依赖、构建前端，启动 API 与单 worker。首次启动需要网络下载安装包。访问 **http://127.0.0.1:8765**，Ctrl+C 停止；再次执行恢复任务。服务只监听本机，禁止非 localhost Host 和跨站 Origin。P0 不支持 LAN 模式或公网暴露，不配置反向代理。

启动前可复制 `.env.example` 为 `.env`，配置 `FAS_MEDIA_ROOT` 为允许注册的绝对路径。数据默认位于应用 `data/`，注册根目录默认 `data/media/`。修改路径后重启。`FAS_DATA_DIR` 切换到另一独立数据库；每个数据目录只允许一个 worker。FFmpeg 自定义路径使用 `FFMPEG_BIN` / `FFPROBE_BIN`。端口用 `FAS_PORT`（默认 8765）。

## 可测试交互

1. 创建训练场次，设置名称与日期；可编辑或删除。
2. 选 GoPro / iPhone / 其他相机；拖入或选择多个视频。XHR 每个文件直接分块写磁盘，显示上传百分比，可取消上传。支持 MP4、MOV、M4V、MKV、AVI、WEBM；扩展名检查后真实解码验证。默认单文件最大 100 GiB，可用 `FAS_MAX_UPLOAD_BYTES` 调整。准备足够磁盘空间。
3. 不复制原文件：把视频放在已批准的媒体根目录，再输入文件或目录绝对路径注册。目录只导入第一层，单次最多 200 个；同场次同路径去重。路径 traversal 与符号链接越界会被拒绝。文件改名、移动或权限失效会产生可查看的错误。
4. worker 顺序执行元数据探测、最长边不超过 1280×720 的 H.264/AAC 24fps 代理与 JPEG 缩略图。保留纵横比，竖屏不拉伸。进度来自 FFmpeg 实际输出，不是模拟计时。成功卡片可播放代理视频，支持 HTTP Range；播放器不访问原片。
5. 等待或运行任务可取消，失败/取消任务可手动重试；错误不会标成成功。不自动无限重试。关闭/崩溃时中断任务在重启后从头重新处理，不是按帧断点续转。子进程监督器使用管道检测 worker 崩溃并终止遗留 FFmpeg，防止恢复时重叠重负载。
6. 删除场次为软删除，隐藏记录并取消未完成任务，**不删除任何原文件或衍生文件**。当前无恢复/清理 UI；若磁盘不足，停止服务并备份后手动管理 `data/`，不要删数据库仍引用的素材。

## 数据与 API

`data/studio.sqlite3`：场次、素材与任务；WAL、外键、事务。`backend/schema.sql` 初始化迁移版本 1，`PRAGMA user_version` 防止打开不支持的新数据库。升级时需增加迁移。上传副本在 `data/uploads/`，代理、日志和缩略图在 `data/derived/<media_id>/`。重启会清理未完成上传的 `.partial`（上传中断不续传）。备份时停止服务后复制整个 data；路径注册素材需单独备份。

- `GET /api/health`：依赖状态、worker 存活、schema_version、approved media root；analysis_available=false。
- `GET/POST /api/sessions`；`GET/PATCH/DELETE /api/sessions/{id}`。
- `POST /api/sessions/{id}/register`：JSON `{path, source}`。
- `POST /api/sessions/{id}/upload?filename=…&source=…`：原始二进制流（非 multipart）。
- `GET /api/jobs`；`POST /api/jobs/{id}/cancel`、`/retry`。
- `GET /api/media/{id}/proxy`、`/thumbnail`：仅提供衍生文件，没有原片下载接口。
- 本地 API 文档：http://127.0.0.1:8765/docs。

请求与响应示例在 `docs/examples.json`；后续分析 provider 设计边界在 `docs/provider-interface.md`，**该接口 P0 未实现**。

## 测试

```bash
cd /Users/claw/Documents/raincoat/apps/football-ai-studio
.venv/bin/python -m pytest tests -q
cd frontend && npm run build
```

测试使用 FFmpeg 生成真实测试图案/音频，不包含模拟识别。覆盖场次 CRUD 与重启、流式上传和限制、目录与 symlink 边界、真实 probe/proxy/thumbnail 和 Range 播放、失败重试、取消、恢复、单 worker 锁、竖屏与短 4K 素材、worker 崩溃子进程清理。运行记录见 `docs/validation.md`。

前端开发可分别运行 `.venv/bin/python -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8765 --env-file .env` 和 `cd frontend && npm run dev`；前端生产构建由 FastAPI 同源提供。

## 已知边界

- 未对真实 40 分钟 4K GoPro + 多段 iPhone 素材验证吞吐、磁盘容量和视频兼容性；短合成 4K 只能验证输入链路，不代表长视频验收通过。
- 原始片可以非常大；上传和 FFmpeg 不把整片放内存，重负载并发为 1，转码时间取决于本机和编码。代理通常明显更小，但仍占磁盘；无容量配额或自动清理。
- HDR/Dolby Vision 未专门做色彩映射，代理色彩可能与原片不同。极端可变帧率/损坏文件/无时长流可能失败，错误保留供重试。
- 无目标儿童标注、人物/事件识别、相机同步、人工事件复核、特效或 16:9/9:16 成片。识别准确率未验证，P1/P2/P3 需用户确认后开发。
- 本机使用，没有登录/多用户协作；不能用于 LAN/互联网访问。无云凭证需求。

没有真实视频时，可执行 `./tests/make_fixture.sh` 生成 4 秒测试图案视频，再在工作台上传或注册打印出的路径。它仅用于导入、播放与预处理检查，不用于识别准确率评测。

本次自动化浏览器读取 Documents 文件遇到访问停滞，改用 `/private/tmp` 副本上传后通过。若浏览器无法读取本地文件，请检查 macOS 文件访问权限，或直接使用批准媒体根目录内的路径注册；详细证据与未确认的原因见验证报告。
