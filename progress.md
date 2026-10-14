# Progress
2026-10-14：确认 P0 范围，创建分支，开始后端开发。
后端与 UI 初版完成，准备实际验证。依赖下载被网络沙箱阻止，改用授权升级安装；首次 npm ci 无锁文件，改用 npm install 生成锁文件。浏览器空间 56。
前端 build 首次通过（28 modules）。pip 默认源未返回 pydantic，切到官方 PyPI 且明确锁定 2.12.3。
pip 在 Python 3.14 下两次未获取 pydantic/core 包，改用应用独立的 bundled Python 3.12 venv 和镜像源安装；不改系统 Python。
Python 3.12 环境依赖安装成功。pytest 正在实际运行，前 7 项通过；启动脚本调整缓存到应用 data，避免依赖用户全局缓存权限。
pytest 实跑：9 passed, 1 warning in 22.52s（第三方 anyio BlockingPortal 弃用警告）。start.sh 实跑构建成功，初次端口绑定被沙箱禁止，升级后 127.0.0.1:8765 已运行。浏览器创建训练场次成功。
浏览器上传第一次等待超时：File 对象存在但读前 100 字节超时，服务端未收到上传，怀疑 macOS 浏览器对 Documents 文件访问；改用 /private/tmp 副本验证。未把该超时记为通过。
临时目录副本浏览器上传成功（3.2 MB），真实预处理完成；代理 H.264 在浏览器实际播放，duration=4.017007，1280x720，currentTime=0.396128，paused=false。Documents 原路径文件读取问题仅在本次浏览器自动化环境出现，临时目录验证通过。
浏览器真实操作：本地注册成功、重复跳过=1、越界目录显示拒绝；损坏 MOV 真实 ffprobe 错误，重试后 attempts=2 仍显示失败；场次编辑成功，临时场次创建/确认删除成功。
浏览器 CDP 截图接口两次超时，未获得截图，不影响 DOM 操作与播放验证。服务启动关闭 access log，避免频繁状态轮询日志过量；TTY Ctrl+C 控制不可靠，使用已知测试 PID 的 SIGTERM 做重启。
最终重启验证：旧进程19913退出，start.sh重启新进程22176。健康status=ok/worker_alive=true；3个卡片与尝试次数保留，代理加载duration=4.017007。TaskSpace56 finish({keep:[p1]})完成，保留可测试页面。完成 P0，停在里程碑。
首次提交后发现仓库全局忽略 .env.example；修正应用 .gitignore 例外并补充配置模板提交。之前一次追加例外命令使用了错误工作目录，已修正。
