Read `<PLUGIN_ROOT>/workflows/common.md` and the inherited provider adapter first.
Use the entrypoint's `<PLUGIN_ROOT>`; this internal playbook is not a public skill.
The shared scope, persistence, worker, and model-capacity rules govern this procedure.

# init-merlean — shared MerLean setup

Prepare the user project and optional Python runtime through the installed script.
Keep `LIB_DIR` outside the plugin cache. Existing environment files are preserved.

```
bash <PLUGIN_ROOT>/scripts/setup.sh --project <LIB_DIR> \
  [--runtime <RUNTIME_DIR>] [--skip-venv] [--skip-mathlib]
```

## Procedure

1. **Backend first.** Without displaying its value, check whether `OPENAI_API_KEY` is available in
   the environment or an existing ignored `.env`. **Never ask the user to paste a key into chat,
   a prompt, or a command argument.** If no key is preconfigured, use the complete deterministic
   fallback by prefixing plan calls with `PLAN_OFFLINE=1`. If the user later wants online Mem0-g,
   tell them to configure the environment variable or ignored `.env` outside the conversation.
2. **Run the script** with `--project <LIB_DIR>` explicitly. The runtime defaults to
   `MERLEAN_RUNTIME` when set, otherwise the plugin root. Use `--runtime <RUNTIME_DIR>`
   for a separate writable/shared runtime and preserve that choice through `MERLEAN_RUNTIME`
   on subsequent CLI calls. Initial setup may take minutes; use background execution with
   progress reporting. Skip flags support scoped setup or already prepared components;
   skipped components are not verified.
3. **Inspect output and verify needed components.** The script prints project/runtime
   locations, not a complete import audit. Verify the configured runtime's `lean_lsp_mcp`
   and `plan_store` imports when needed, and `lake` availability for Lean work. Missing Lean
   requires the Lean/elan prerequisite. Runtime failures require the actual error and a
   scoped repair or another runtime directory; preserve existing incomplete runtimes.
4. **MCP loading.** If `.mcp.json` was created, follow the provider adapter's reload guidance.

## What the script does (all idempotent)
| step | action |
|---|---|
| venv | prepare `<RUNTIME_DIR>/.venv/` from `src/requirements.txt` (host python ≥ 3.9, else `uv` fallback) |
| .env | preserve an existing ignored file; otherwise leave a local placeholder and use offline mode |
| .mcp.json | created from `templates/mcp.json` when absent, otherwise preserved — registers the `lean-lsp` MCP server, run from the venv python |
| Lean workspace | create missing project templates; run `lake update` only for a newly created Lake project, then cache retrieval/build unless skipped; synchronize only a newly created toolchain |
| output | report project/runtime locations and any missing setup component |

Existing project files (`.env`, `lean-toolchain`, `lakefile.toml`, `MerLeanExperiment.lean`) are
**never overwritten**, including `.mcp.json`. Re-running after a failed step is safe.

After setup, the plan-graph CLI is invoked as
`<PLUGIN_ROOT>/scripts/merlean --data <DATA_DIR> <command>`
with `MERLEAN_RUNTIME` when configured — see `workflows/plan-graph.md`.
