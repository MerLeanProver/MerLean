# Codex adapter

Run the selected public agent in the main context. Resolve `<PLUGIN_ROOT>` from its
installed `skills/<name>/SKILL.md`: three parent directories from the file. Internal
workflow and role files never change this root. Do not infer it from the project cwd.

Use available Codex subagent tools for the internal roles in `roles/`; read the role
file before dispatch and pass its bounded contract to the worker. Do not invoke missing
public specialist skills. Obey host concurrency (normally three children in four total
slots); keep the plan graph single-writer. Main and GPT workers default to `gpt-6-astra`,
unless explicitly overridden. No silent model fallback. Capacity recovery is in
`workflows/common.md`; it cannot restart an unavailable host main model.

Use the available Lean MCP tools; `lake build` and Heavy's runtime certificate audit
remain authoritative. The setup script creates a project `.mcp.json` descriptor, but
Codex may require registering that command with its own MCP configuration: do not claim
that a project JSON file automatically installs an MCP server. If no server is loaded,
use Lean CLI diagnostics or explain the required host configuration.

For new paper-writing runs, read `workflows/paper-recursive-writing.md` and dispatch its
internal planner, writer, and four checker roles using existing host subagent tools. With
three child slots, review in parallel waves; collect all four reports before replanning.
Whole-paper objectives are normal, not an exception to a forced micro-task rule. Checkers
receive frozen snapshots and their own prior feedback, not peers' current verdicts. Main
alone applies worker patches and registers state. No standalone launcher or extra login is
needed. Preserve schema-version-1 saved runs under the retained legacy paper protocol.

Use the same `paperctl` checks as Claude. Internal historical
tool labels such as Task, Read, or Grep mean the corresponding available Codex tools,
not permission to assume a nonexistent API.
