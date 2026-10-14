# Football AI Studio P0
目标：新分支交付本地可交互工作台；只到 P0，无 AI 识别/云传输。
1. 需求与环境：complete（用户授权直接开发，默认 data/media）
2. API、迁移、持久 worker、真实 FFmpeg：complete
3. React 工作台、启动脚本、文档：complete
4. 自动测试、浏览器交互、服务重启与交付：complete
验收：9 passed；build 通过；浏览器导入/播放/注册/重试/CRUD/重启保留均通过。
边界：无真实长足球素材，40min 4K 吞吐未验证，P1 未开发；只做短合成视频链路。
错误与处置：git/下载/端口沙箱通过授权升级完成；默认源依赖失败改 Python3.12+镜像；浏览器 Documents 文件读取失败改 tmp 副本验证，真实根因未知；CDP 截图失败无截图交付。
详情：apps/football-ai-studio/docs/validation.md。
