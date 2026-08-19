---
name: init-merlean
description: Set up the standalone Codex MerLEAN plugin — build its Python .venv from src/requirements.txt, write the plugin .mcp.json for lean-lsp, ensure an OpenAI key in .env, and optionally prepare the bundled Lean + Mathlib workspace. Use when asked to install, set up, initialize, or redeploy this Codex MerLEAN port, or when a fresh copy needs its runtime prepared.
---

# init-merlean — one-command Codex MerLEAN setup

`skills/` and `src/` are tracked in this plugin, so there is nothing to "deploy":
this skill prepares the **runtime** only. Everything is done by one idempotent, non-interactive
script:

```
bash <PLUGIN_ROOT>/skills/init-merlean/scripts/setup.sh \
  [--openai-key sk-...] [--skip-venv] [--skip-mathlib]
```

## Procedure

1. **Backend first.** The Codex mode name `init-merlean` is the normalized spelling of the
   upstream Claude command `init_merlean`. Check whether an OpenAI key is already reachable:
   `.env` at the repo root
   contains `OPENAI_API_KEY=sk-...`, or `OPENAI_API_KEY` is set in the environment. If neither,
   ask the user for their key only when they want the online Mem0-g embeddings/reranker. They may
   instead use the complete deterministic fallback by prefixing plan calls with `PLAN_OFFLINE=1`.
2. **Run the script** (from the repo root):
   - key in hand → `bash <PLUGIN_ROOT>/skills/init-merlean/scripts/setup.sh --openai-key <KEY>`
   - key already reachable, or user skipped → `bash <PLUGIN_ROOT>/skills/init-merlean/scripts/setup.sh`
   - The Mathlib step (`lake update` + `lake exe cache get` + `lake build`) can take many
     minutes on first run — run it with a generous timeout or in the background. Pass
     `--skip-mathlib` only if the user asks for a quick/venv-only setup.
3. **Read the check block** the script prints at the end. All three must be `[ok]`:
   `lean-lsp-mcp` importable from the venv, `lake` on PATH, `plan_store` importable.
   - `lake not found` → tell the user to install Lean via `elan`
     (https://leanprover-community.github.io/get_started.html), then re-run this skill.
   - venv failures → the script already tried `ensurepip`/`get-pip` and a `uv` fallback;
     report the pip error to the user.
4. **Restart note.** If `.mcp.json` was just created, tell the user the `lean-lsp` MCP
   server loads in a new Codex thread after the plugin is reloaded.

## What the script does (all idempotent)
| step | action |
|---|---|
| venv | build `.venv/` from `src/requirements.txt` (host python ≥ 3.9, else `uv` fallback) |
| .env | write from `--openai-key`, else preserve an existing key, else leave the template |
| .mcp.json | created from `templates/mcp.json` when absent, otherwise preserved — registers the `lean-lsp` MCP server, run from the venv python |
| Lean workspace | copy `lean-toolchain` / `lakefile.toml` / `MerLeanExperiment.lean` to the root if missing, then `lake update` + `lake exe cache get` + `lake build` (toolchain auto-synced to Mathlib's) |
| checks | `lean-lsp-mcp` import, `lake` on PATH, `plan_store` import |

Existing root files (`.env`, `lean-toolchain`, `lakefile.toml`, `MerLeanExperiment.lean`) are
**never overwritten**, including `.mcp.json`. Re-running after a failed step is safe.

After setup, the plan-graph CLI is invoked as
`<PLUGIN_ROOT>/scripts/merlean --data <DATA_DIR> <command>`
(Windows/Git Bash: `.venv/Scripts/python.exe`) — see the `plan-graph` skill.
