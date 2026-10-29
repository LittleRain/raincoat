# raincoat-create-report

将标准化的业务需求制作成可复用的报告 Skill。先按 SKILL.md 的模板和本地向导整理需求，再生成包；不会自动实现业务算法。

## 独立使用

依赖 Python 3.10+，标准库即可；不要求克隆 Raincoat。向导位于 assets/intake-wizard.html，可本地打开。

```bash
python scripts/create_report_skill.py raincoat-my-report "My Report" /path/spec.md /path/source.md L0 --output-root /path/output
python scripts/build-output-inventory.py --spec /path/spec.md --output /path/inventory.json
python scripts/validate-output-inventory.py --inventory /path/inventory.json --html /path/report.html
python -m unittest discover -s tests -p 'test_*.py'
```

默认输出当前工作目录的 skills/，拒绝覆盖已有目录。Bash 入口保留相同位置参数，新增 --output-root。生成器全部使用包内模板。

L0 为文档草案，运行入口明确失败。L1/L2 必须提供 --evidence-dir，验证所需文件后复制 scripts、sample_data、output；提供证据不代表生成器已独立验证其真实性。证据可能含私有内容，输出包只保存在用户指定本地位置，发布前必须审阅。不会自动上传或安装依赖。

## 状态

草案；macOS/Python 独立合成验证，Windows 与宿主自动发现未实测。L1/L2 的 Bash 运行证据不代表 Windows 原生运行。许可尚待确认，不能正式发布；不自动向下游授予许可证。

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
