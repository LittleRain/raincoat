# Unified local agent MCP implementation plan

Goal: delegate tasks to Bitto or WorkBuddy through one MCP, preserving runtime/model/account routing, and return completed results promptly.

Architecture: one persistent job store and detached worker per job; backend selected explicitly at submission. Reuse the tested Bitto protocol adapter; WorkBuddy runs its bundled CLI with in-memory credentials. A private Unix socket lets callers wait for completion immediately; legacy workers fall back to short bounded status polling. Submission waits up to 25 seconds by default, then returns a job ID for repeated bounded waits. Completion is never inferred from an intermediate assistant message.

Files: bridge.py (store, workers, CLI, MCP), workbuddy.mjs (credential/CLI adapter), tests/ (regressions and live integration), config/ (generated local config), README.md. Existing Bitto adapter remains a supported implementation dependency and old jobs remain readable.

- [x] Reproduce absent completion-wait seam and cover prompt completion return, cancellation, permission and historical-run handling.
- [x] Implement backend routing and private socket completion waits, retaining job persistence and old-job compatibility.
- [ ] Implement WorkBuddy streaming results, explicit tool allowlists, resume/cancel, redaction and fail-closed error handling.
- [ ] Verify unit tests, both real backends, wait latency, resumed sessions and cancellation.
- [ ] Register one MCP in Codex/DeepSeek Harness, retaining a backed-up previous config and legacy tool compatibility.
- [ ] Commit only MCP changes on codex/local-agent-mcp. Do not merge or push without a new request.

Validation: completion is defined by Bitto SessionRunEnded or WorkBuddy result frame; measured completion-to-return latency should be below 250 ms locally, and synthetic tests must catch a 5-second polling delay. Do not promise an unsolicited client callback: MCP tools return results when called; callers should keep a bounded wait outstanding.

## Checkpoint 2026-10-22

Branch: codex/local-agent-mcp. Bitto implementation and bounded waits pass 13 regressions and real MCP execution; latest completion delivery 1.972 ms. Review fixes include bounded socket notifications, child reaping and zombie detection, legacy session locks, and cancellation races.

WorkBuddy full adapter remains unimplemented. Automatic approval review rejected creating persistent credential reuse from desktop www.codebuddy.cn credentials to www.workbuddy.cn because previous permission covered one verification only. User has been asked asynchronously whether to authorize this for future explicitly delegated WorkBuddy jobs; no reply yet. Do not implement or exercise that credential transfer until authorized. Discovery returns execution_ready=false and submission fails before creating a job. Do not represent WorkBuddy as enabled.

No client registrations changed. Generated configurations are previews only. Next: obtain authorization, implement the WorkBuddy adapter, validate result/resume/cancellation, activate a single backed-up registration, and commit completion. No merge or push requested for this branch.
