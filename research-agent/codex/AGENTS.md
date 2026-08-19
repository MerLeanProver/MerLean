# MerLEAN for Codex

This folder is a standalone Codex plugin port of the parent MerLEAN Claude package.

- `skills/` contains every workflow mode and specialist role.
- `src/` is the single plan-graph implementation.
- Resolve the plugin root from the active skill's source path; never assume the user's current
  directory is the plugin root.
- Invoke the graph only through `<PLUGIN_ROOT>/scripts/merlean`. Set `PLAN_OFFLINE=1` explicitly
  when the deterministic local backend is required; otherwise the online Mem0-g backend remains
  the default.
- The plan graph is an embedded single-writer store. The main orchestrator owns mutations.
- Codex subagents share the workspace. Give each an exclusive file and never use Claude worktree
  copy/patch instructions.
- Respect the runtime's concurrency cap. With four total slots including the main agent, run at
  most three subagents concurrently even where the upstream text says four.
- Strict mode means no `sorry`, `admit`, project axioms, or weakened statements. Final success
  requires a whole-library build, a clean duplicate lint, and an axiom audit of each root theorem.
