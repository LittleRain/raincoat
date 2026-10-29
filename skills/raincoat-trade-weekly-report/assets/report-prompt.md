# 周报生成 Prompt

Generate the HTML weekly report from the embedded contract and declared data
contracts only.

Rules:

- use only metrics and fields declared in the normalized spec
- keep the validated section order
- include charts, tables, and conclusion blocks where required
- block unsupported analysis instead of guessing
- follow declared table schemas and WoW rules exactly when present
- classify `非ACG-加林 / 头部UP` from head UP list by store ID (fallback to merchant/up_mid if needed)
- do not claim runnable output unless real execution and verification exist
