# Claude Code adapter

Run the selected public agent in the main context. `<PLUGIN_ROOT>` is
`${CLAUDE_PLUGIN_ROOT}` when provided by Claude Code, otherwise the directory three
parents above the installed `skills/<name>/SKILL.md`. Internal references do not reset it.

Read `roles/<role>.md` and dispatch its bounded instructions using available Claude Code
Task/subagent tools. Background workers own disjoint files; the main agent alone writes
the plan store. The old named specialist agents are internal roles, not extra public
agents. Use the available concurrency, never more than four children, and retain the
signature-locked scheduling and independent audits.

Preserve the user's configured Claude model. GPT research calls, when explicitly
available, default to `gpt-6-astra`; do not replace Anthropic model identifiers with GPT
identifiers. Read `workflows/common.md` for capacity recovery and authority limits.

For project setup use `scripts/setup.sh --project <LIB_DIR>`; reload the host to pick up
a newly created project `.mcp.json`. If Lean MCP is unavailable, use `lake build` and Lean
CLI diagnostics. `<PLUGIN_ROOT>/scripts/merlean` works in both online and explicit
`PLAN_OFFLINE=1` modes, with optional `MERLEAN_RUNTIME` for a writable external venv.

Paper-writing uses the same deterministic `paperctl` preservation/refinement checks as
Codex. Its historical Claude eight-step presentation protocol is retained as an internal
reference; it does not replace the shared reference, baseline, and completion gates.
