# Legacy report generator

Moved byte-for-byte from `docs/周报生成器_v3/` during directory migration. This entrypoint is retained because its input contract and classification differ from the current six-file generator. It requires `app.js` beside it.

Use `python generate_report.py --help` for its actual `--dir` / `-o` interface. Legacy inputs use file patterns such as 整体数据、区分行业、分行业x流量渠道、分行业x内容类型 and optional product tables / 头部UPlist; they are not interchangeable with the current six-file input set. Both implementations use the declared pandas/numpy/openpyxl dependencies.

This is retained compatibility code, not the default entrypoint and not a validated replacement for the current runtime. Synthetic smoke coverage and the known differences are recorded in the migration validation document. Original private spreadsheets and reports remain outside the distributable skill resources.

Original usage guide: [INPUTS.md](INPUTS.md).
