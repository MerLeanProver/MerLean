# plan_store — Mem0-g plan graph (Phase 1)

Replaces `statements.json` / `progress.json` with a **Mem0 2.x graph**: each
statement is one memory node (`infer=False`), and the **dependency edges live in
node metadata, kept equal to the real Lean dependency graph** (pure helpers
from the predecessor plan store are vendored copies under `_vendor/`).

## Run

Use the shared `.venv` (Mem0 2.x + spaCy, installed from `src/requirements.txt`
via the `init-merlean` skill — `bash skills/init-merlean/scripts/setup.sh`):

```bash
# .venv/bin/python on Linux/macOS, .venv/Scripts/python.exe on Windows
PY=.venv/bin/python
$PY src/cli.py --data <DATA_DIR> <command> [...]
```

State for each target lives in a data folder next to the target file (`<file>_data/`,
git-ignored). The OpenAI key is read from `.env` (or the `OPENAI_API_KEY` env var).

## Commands

| Command | Purpose |
|---|---|
| `import-json PATH` | load a `statements.json` (+ sibling `progress.json`/`corrections.json`) |
| `export-json [--out P]` | emit `statements.json` + `progress.json` from the graph |
| `list [--status S] [--kind K]` | list nodes (id/type/name/status/deps); `--kind formal\|informal\|all` |
| `get SID` | print one node (all metadata) |
| `topo` | statement ids in dependency order (deterministic) |
| `cone SID [SID...]` | forward (downstream) dependency cone — for invalidation |
| `cycles` | dependency cycles (empty = clean DAG) |
| `set-status SID STATUS` | `pending\|in_progress\|completed\|completed_axiom\|failed` |
| `update SID --json '{...}'` | merge fields into a node |
| `add --json '{...}'` | add a node (dict with at least `id`); `"type": "Note"` adds an informal note |
| `delete SID` | delete a node |
| `sync-lean LIB_DIR` | **rewrite edges from the real `.lean` files** (graph == Lean dep graph) |
| `search QUERY [--top-k N] [--kind K]` | semantic search → `{"formal": [...], "informal": [...]}`, ranked separately |
| `reset` | wipe the library's store (filesystem) |

All output is JSON on stdout (for skills to parse).

## Node metadata

`statement_id, type, name, content, dependencies[], dependents[], proof, anchor,
mathlib_types, lean_path, hierarchy_level, corrections[], status, do_not_import[],
declarations_defined[], imports[], source_start, source_end, order`.

`status` subsumes `progress.json` (`completed_ids` = nodes whose status is
`completed`/`completed_axiom`). `dependencies` is the graph; `sync-lean` makes it
equal to the actual symbol-level dependencies among the generated `.lean` files
(via the vendored `DependencyAnalyzer`).

**Informal nodes** (`type: "Note"`, plus the auto-generated `Summary`) are embedded for
search but excluded from the graph, topo/levels, status, export, and `sync-lean`. Notes
carry provenance fields: `confidence, source, evidence, method, caveats, related[],
created, updated` (`created`/`updated` stamped automatically). They hold research
conclusions — beliefs with evidence — and are updated/deleted when a kernel-checked
formal result contradicts them.

## Layout

```
plan_store/
  config.py     Mem0 config (OpenAI + embedded Qdrant per library, telemetry off)
  store.py      PlanGraph — the statement_io contract over Mem0
  lean_sync.py  edges + Lean detail from the real .lean files
  compat.py     statements.json import/export
  __main__.py   CLI
  _vendor/      verbatim copies: models, toposort, cone, lean_parser
  tests/        synthetic fixture + verify_phase1.py (15 checks, all passing)
```

## Verify

```bash
.venv/bin/python src/plan_store/tests/verify_phase1.py
```
Checks round-trip, topo/cone parity with the vendored algorithms, status/progress,
`sync-lean` reconciling edges to the real Lean graph, and semantic search.
