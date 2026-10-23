# Local package distribution implementation plan

Goal: ship raincoat-agent-mcp as a locally installed Python tool with a fixed entry point, one-command updates, backend dependency discovery, client setup, and reproducible releases.

Approved approach: uv tool install/upgrade; each user's local Bitto/WorkBuddy runtime and credentials stay on that user's machine. Current backend support is macOS only. Public publishing is outside this change; prepare artifacts and a tag-triggered workflow.

- [x] Package existing adapters under src/raincoat_agent_mcp, include the Node runner, preserve source bridge.py and installed-job protocol compatibility. Add version metadata and local-agent entry point.
- [x] Add setup for Codex, DeepSeek Harness profiles and generic MCP JSON, with previews/backups and stable uv environment commands. Preserve unrelated settings.
- [x] Add doctor for platform, runtimes, Node 22.19+ (22.x) or >=24 and the pinned isolated WorkBuddy helper. --install-deps invokes npm only on explicit request and stores non-secret runtime paths.
- [x] Add --version, update --check, normal upgrade, local-wheel upgrade and version rollback. Guard non-uv installs and in-flight jobs; never silently update during MCP calls.
- [x] Add local wheel/sdist builds and trusted-publishing workflow, including version/tag consistency and model-free tests.
- [x] Test package contents, install and MCP handshake outside the checkout, upgrade between two local wheel versions, setup idempotence, failure paths, and full regressions.
- [x] Rewrite README for recipients and maintainers, including unpublished status, supported platforms, prerequisites, migration and reload requirements. Commit on codex/local-agent-mcp; no merge/push/publication.

Files: pyproject.toml, src/raincoat_agent_mcp/{cli,management,client_config,dependencies,updates}.py; original protocol modules move into that package. Compatibility wrappers remain at bridge.py/install.py/configure.py. Tests cover installed distribution and CLI management. CI lives at .github/workflows/raincoat-agent-mcp-release.yml.
