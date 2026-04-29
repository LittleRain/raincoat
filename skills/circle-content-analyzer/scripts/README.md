# scripts

这个目录预留给 `circle-content-analyzer` 的正式运行时代码。

## 运行时要求

正式入口应满足：

- 输入三张 Excel：讨论区、票务进入圈子、T3 进入圈子
- 输出本地 HTML 和 JSON
- 默认不联网上传
- 只有显式 `--upload` 时才允许上传 HTML
- 不保留个人绝对路径常量
- 支持从历史快照读取上一期结果做对比

## 最低验证要求

1. `python3 -m py_compile scripts/*.py`
2. 用真实三张 Excel 跑一次
3. 检查 HTML/JSON 是否成功生成
4. 检查 `uv_expose > 100` 的结论过滤是否生效
5. 如果启用上传，先提示用户并征得同意
