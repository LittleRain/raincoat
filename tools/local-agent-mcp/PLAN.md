# Unified local agent MCP implementation plan

Goal: delegate tasks to Bitto or WorkBuddy through one MCP, preserving runtime/model/account routing, and return completed results promptly.

Architecture: one persistent job store and detached worker per job; backend selected explicitly at submission. Reuse the tested Bitto protocol adapter; WorkBuddy runs its bundled CLI with in-memory credentials. A private Unix socket lets callers wait for completion immediately; legacy workers fall back to short bounded status polling. Submission waits up to 25 seconds by default, then returns a job ID for repeated bounded waits. Completion is never inferred from an intermediate assistant message.

Files: bridge.py (store, workers, CLI, MCP), workbuddy.mjs (credential/CLI adapter), tests/ (regressions and live integration), config/ (generated local config), README.md. Bitto protocol code is reused in an independent adapter; the original MCP directory is untouched and old jobs remain readable.

- [x] Reproduce absent completion-wait seam and cover prompt completion return, cancellation, permission and historical-run handling.
- [x] Implement backend routing and private socket completion waits, retaining job persistence and old-job compatibility.
- [x] Implement WorkBuddy streaming results, explicit tool allowlists, resume/cancel, redaction and fail-closed error handling.
- [x] Verify unit tests, both real backends, wait latency, resumed sessions and cancellation.
- [x] Register one MCP in Codex/DeepSeek Harness, retaining a backed-up previous config and legacy tool compatibility.
- [x] Commit only MCP changes on codex/local-agent-mcp. Do not merge or push without a new request.

Validation: completion is defined by Bitto SessionRunEnded or WorkBuddy result frame; measured completion-to-return latency should be below 250 ms locally, and synthetic tests must catch a 5-second polling delay. Do not promise an unsolicited client callback: MCP tools return results when called; callers should keep a bounded wait outstanding.

## Verification 2026-10-23

User explicitly authorized persistent reuse of existing desktop www.codebuddy.cn credentials for future WorkBuddy tasks authenticated at www.workbuddy.cn. The adapter reads existing credentials without refresh and passes them only in the local CLI child environment; bridge logs redact token values.

Bitto real MCP execution passed with 1.972 ms completion delivery. WorkBuddy real MCP execution passed with 1.261 ms, verified output artifact 339, resumed the same CLI session and verified history, and cancelled a real Python command with child termination confirmed. Synthetic regressions cover large results, subscription races, dead/zombie workers, original Bitto locks, authoritative final results, permission denial, group cleanup including signal-ignoring descendants, and immediate resume during cleanup.

Client migration uses backed-up config replacement and a stable per-user installed runtime release. No merge or push requested for this branch.

Final verification: 29 unified regressions and 9 original Bitto regressions pass. Installed runtime was loaded from actual Codex registration (11 tools), both backend status calls passed, and the historical Bitto task retained its 55 tool-call records. Installed WorkBuddy execution completed with 1.963 ms delivery; same-session resume and real Python cancellation passed. Checked 58 bridge artifacts in memory against the current credential values and found zero token leaks. Both client configurations were parsed and compared against backups to confirm unrelated settings unchanged. Stable Node discovery also passed with a minimal desktop PATH.
