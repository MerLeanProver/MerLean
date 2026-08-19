---
name: init_merlean
description: Set up the MerLEAN system in this repo (replaces the old src/deploy.sh) — build the shared Python .venv from src/requirements.txt, write the root .mcp.json for the lean-lsp MCP server, ensure an OpenAI key in .env, and prepare the root Lean + Mathlib workspace (lake update / cache get / build). Use when asked to install, set up, initialize, or (re)deploy MerLEAN, or when a fresh clone needs its runtime prepared.
---

# init_merlean — one-command MerLEAN setup

`.claude/` (skills + agents + settings) is tracked in git, so there is nothing to "deploy":
this skill prepares the **runtime** only. Everything is done by one idempotent, non-interactive
script:

```
bash .claude/skills/init_merlean/setup.sh [--openai-key sk-...] [--skip-venv] [--skip-mathlib]
```

## Procedure

1. **Key first.** Check whether an OpenAI key is already reachable: `.env` at the repo root
   contains `OPENAI_API_KEY=sk-...`, or `OPENAI_API_KEY` is set in the environment. If neither,
   ask the user for their key (it is required by the Mem0-g plan graph for embeddings/rerank);
   they may also skip and fill `.env` in later.
2. **Run the script** (from the repo root):
   - key in hand → `bash .claude/skills/init_merlean/setup.sh --openai-key <KEY>`
   - key already reachable, or user skipped → `bash .claude/skills/init_merlean/setup.sh`
   - The Mathlib step (`lake update` + `lake exe cache get` + `lake build`) can take many
     minutes on first run — run it with a generous timeout or in the background. Pass
     `--skip-mathlib` only if the user asks for a quick/venv-only setup.
3. **Read the check block** the script prints at the end. All three must be `[ok]`:
   `lean-lsp-mcp` importable from the venv, `lake` on PATH, `plan_store` importable.
   - `lake not found` → tell the user to install Lean via `elan`
     (https://leanprover-community.github.io/get_started.html), then re-run this skill.
   - venv failures → the script already tried `ensurepip`/`get-pip` and a `uv` fallback;
     report the pip error to the user.
4. **Restart note.** If `.mcp.json` was just (re)generated, tell the user the `lean-lsp` MCP
   server loads on the next Claude Code session start.

## What the script does (all idempotent)
| step | action |
|---|---|
| venv | build `.venv/` from `src/requirements.txt` (host python ≥ 3.9, else `uv` fallback) |
| .env | write from `--openai-key`, else preserve an existing key, else leave the template |
| .mcp.json | generated from `templates/mcp.json` — registers the `lean-lsp` MCP server, run from the venv python |
| Lean workspace | copy `lean-toolchain` / `lakefile.toml` / `MerLeanExperiment.lean` to the root if missing, then `lake update` + `lake exe cache get` + `lake build` (toolchain auto-synced to Mathlib's) |
| checks | `lean-lsp-mcp` import, `lake` on PATH, `plan_store` import |

Existing root files (`.env`, `lean-toolchain`, `lakefile.toml`, `MerLeanExperiment.lean`) are
**never overwritten** (only `.mcp.json` is regenerated). Re-running after a failed step is safe.

After setup, the plan-graph CLI is invoked as
`.venv/bin/python src/cli.py --data <DATA_DIR> <command>`
(Windows/Git Bash: `.venv/Scripts/python.exe`) — see the `plan-graph` skill.
