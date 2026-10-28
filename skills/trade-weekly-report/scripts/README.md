# Report runtimes

- `run_report.py`：跨平台参数与输入文件校验；支持 --input-dir / --output-dir / --output，保持旧位置参数。
- `run-report.sh`：可选 Bash 兼容入口，不自动安装依赖。
- `generate_report.py`：当前六文件合同，样式在 Skill assets 中。
- `requirements.txt`：pandas、numpy、openpyxl。
- `legacy/`：原 docs/周报生成器_v3 的不同版本，代码与 app.js 保持原字节，不是默认入口。
- `app.js`：保留的历史前端文件；当前默认生成器直接生成图表脚本，不依赖此文件。

实际命令与合同见 [README](../README.md)。
