<!-- BEGIN merlean -->
# MerLEAN — Lean 4 formalization system (Claude Code + Codex)

Autonomous Lean 4 + Mathlib theorem-proving driven by a **Mem0-g plan graph**. The
plan-graph package lives in `src/` (single source of truth); the skills and subagent
roles live in `.claude/`. Both are hand-maintained and tracked in git.

## Environment
- Shared Python venv (built by `/init_merlean`): `.venv/bin/python`
- OpenAI key: `.env` (`OPENAI_API_KEY=…`) or the `OPENAI_API_KEY` env var.
- Plan-graph CLI (run from the repo root):
  ```
  .venv/bin/python src/cli.py --data <DATA_DIR> <command>
  ```
  `<DATA_DIR>` is the data folder next to the target Lean file (`<file>_data/`).
  The graph holds **formal statement nodes** plus **informal notes** (`type: "Note"` —
  research conclusions with provenance); `search` returns the two groups separately.
- MCP: `lean-lsp` via the shared venv (`.venv/bin/python -m lean_lsp_mcp`), registered in
  `~/.codex/config.toml` for Codex and `.mcp.json` for Claude Code. No `uv`/`uvx` needed;
  requires a Lean toolchain (`lake`) on PATH.

## Workflows (invoke as `/<name>`)
- **/auto-research** — Auto-research mode — take an OPEN QUESTION in informal natural language, FORMALIZE it into a Lean 4 statement `:= by sorry`, then RELENTLESSLY resolve it — prove or disprove, no axioms, no stopping, FULLY AUTONOMOUS (never asks the user; ambiguity decided by canonical reading, documented + banked); races a portfolio of 2–3 genuinely different routes in parallel, killing/replacing dead ones; manages its own subagent fleet + RAM; plan graph as persistent memory.
- **/formalize** — Orchestrate formalizing a paper (or filling sorries) into verified Lean 4, using the Mem0-g plan graph as the statement store. Run this in the MAIN context. It…
- **/formalizeproblem** — Turn an INFORMAL mathematical problem into faithful, type-checking Lean 4 statement(s) with `:= by sorry` — translation only, no proving. Careful with ill-posed problems — it surfaces inequivalent readings and asks before committing.
- **/lite-research** — MerLean-lite: NL-first fast mode — parallel representation-hunting routes, step-ledger proofs under adversarial skeptic debate + Python experiment screening, Lean 4 fired ONLY at the triaged weakest links (hypothesis-mode certificates: one contested step proved from its accepted priors as hypotheses). Graded BRONZE/SILVER; GOLD = handoff to /auto-research. The inverse verification budget of /auto-research.
- **/plan-graph** — Read, edit, and SEMANTICALLY SEARCH the formalization statement plan stored in the Mem0-g plan graph (the replacement for statements.json) — inspect/query/modify statements, dependencies, status, informal notes; Lean dependency sync; meaning-based search (embedding recall → LLM rerank).
- **/prove** — Prove mode — fill the `sorry`/`admit` placeholders in an existing Lean file with real proofs, using the Mem0-g plan graph + compile-fix subagent. Run in the MA…
- **/write-paper** — Paper-writing agent — drive a finished campaign through the gated 8-step protocol in `paper-writing-agent/claude/AGENT.md`; artifacts in `<campaign>/paper/`.

## Subagent roles (invoke as `/<name>`, or run inline in Codex)
- **/compile-fix** — Iteratively fix ONE Lean 4 file until it compiles clean (0 errors, 0 warnings, lean-lsp diagnostics), without weakening the statement. Use as a SUBAGENT during formalization — i…
- **/explore** — Research a given subtopic — web search, numerical experiments, downloading useful tools — and return a definite, evidence-backed answer with methods and caveats. Read-only toward the repo; works in scratch space.
- **/route-scout** — Pitch ONE high-level route from an ASSIGNED angle: the representation (why the obstruction shrinks), a 3–7 step skeleton, the predicted weakest step, a ≤5-min kill-test. Same-strength rephrasings rejected at birth.
- **/nl-prover** — Develop one route into a complete step-ledger NL proof (or repair it against objections): self-contained claims, explicit `uses`, honest ROUTINE/COMPUTATION/NOVEL classes, candid own-confidence ranking.
- **/skeptic** — Adversarially audit a step ledger (gaps, circularity, interface lies, class fraud, falsification runs, known-false checks); per-step objections with severity + what-would-resolve; distinguishes "resolved" from "conceded-by-exhaustion" (feeds Lean triage).

## Codex compatibility notes
- Codex is **single-agent**: Claude Code dispatches `compile-fix` as parallel
  background subagents; in Codex, run each role inline (or via its matching skill/prompt) and
  treat *background / ≤4 concurrent* as sequential. The outcome is the same, just slower.
- The plan store is a **single-writer** embedded Qdrant — never open it (`cli.py`) from two
  processes at once.
- On macOS/Linux the venv python is `.venv/bin/python` (Windows uses the path above).
<!-- END merlean -->
