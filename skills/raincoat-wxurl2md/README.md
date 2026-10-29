# raincoat-wxurl2md

使用本地 Chrome 抓取用户有权访问的企微文档，将原始证据与供 AI 使用的 Markdown 分开保存。当前仍为内部草案，名称暂未迁移为 raincoat- 前缀。

## 独立安装

单独复制本目录即可，不需要 Raincoat 的 tools 或根 node_modules。需要 Node.js 18+、Python 3.10+ 与已安装的 Google Chrome。Python 归档器仅用标准库。

```bash
npm ci
node scripts/wecom_capture_opendoc.js --help
```

Playwright 依赖版本由本目录 package-lock.json 锁定；脚本使用已安装的 Chrome channel，安装 npm 包不代表 Chrome 已安装。不要将普通 Chrome Profile 复制进项目或版本库。

## 使用

在本 Skill 目录下执行；`scripts/` 路径也可以替换成安装位置的绝对路径，从其他 cwd 调用：

```bash
node scripts/wecom_capture_opendoc.js --url "https://doc.weixin.qq.com/doc/w3_example" --out-dir output --wait-ms 12000
```

默认会启动独立 Chrome 窗口，使用用户主目录下 `.raincoat-wxurl2md/chrome-profile`。首次可能需要登录，此 Profile 不自动共享普通 Chrome 登录态。`--profile-dir` 或 `WXURL2MD_PROFILE_DIR` 可指定既有的专用抓取 Profile；不要同时用其他进程打开同一 Profile。

输出默认放系统临时目录；推荐显式指定 `--out-dir`。Python 默认 macOS/Linux 为 `python3`，Windows 为 `python`，可用 `--python` 或 `WXURL2MD_PYTHON` 指定解释器完整路径（不是包含参数的 shell 命令）。

Bash 可选批量入口：

```bash
bash scripts/run-wecom-doc.sh --url-file urls.txt --out-dir output
```

URL 文件每行一个地址，空行与 `#` 注释跳过；任一条失败则批次返回非零。`WXURL2MD_CAPTURE_SCRIPT` 继续支持自定义抓取脚本。原 `--no-open` 参数保留为兼容空操作；包装器不再通过 AppleScript 操作普通 Chrome，浏览器由抓取脚本启动。

已有离线导出文本可单独转换，不安装 npm 或访问网络：

```bash
python scripts/wecom_archive.py --draft decoded.md --structured tables.md --out-dir output
```

## 输出与边界

`*_for_ai.md` 优先保留内容，`*_ai_accuracy.md` 更严格清洗；重要结论或数值缺失时回查 raw/keyframe。抓取会请求指定企微文档并在本地保存网络响应及内容，文件可能含文档业务信息。默认不将报告上传到其他服务，不发送消息。

## 验证

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

离线测试覆盖参数、脚本定位、原文保存、数字保留与失败返回，不访问真实文档。迁移后未实测真实登录抓取、Windows Chrome 或全新浏览器授权；不能据此声称全平台支持。旧仓库级命令已改为本目录 scripts 下入口，依赖无需根 package.json。

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
