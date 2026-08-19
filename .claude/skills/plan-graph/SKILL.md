---
name: plan-graph
description: Read, edit, and SEMANTICALLY SEARCH the formalization statement plan stored in the Mem0-g plan graph (the replacement for statements.json). Use whenever you need to inspect, query, or modify statements, dependencies, status, or informal notes; run the Lean dependency sync; or find statements/notes by MEANING (LeanSearch-v2-style two-stage retrieval: OpenAI embedding recall → LLM rerank) — e.g. to check whether a statement already exists before adding one, or to surface prior research knowledge. Wraps the `plan_store` CLI.
---

# plan-graph — drive the Mem0-g statement plan

The plan (every statement + its dependencies + status) lives in a Mem0 2.x graph, not in
`statements.json`. Each statement is one node; the `dependencies` adjacency IS the graph and
is kept equal to the real Lean dependency graph by `sync-lean`. You drive it through one CLI.
The graph also holds **informal notes** (`type: "Note"` — research conclusions with
provenance, see below): searchable next to the formal statements but excluded from the
dependency graph, topo/levels, dashboard, export, and Lean sync.

## Invocation
Always use the shared `.venv` python, from the repo root (Windows/Git Bash:
`.venv/Scripts/python.exe`):
```
.venv/bin/python src/cli.py --data <DATA_DIR> <command> [...]
```
(Set up the venv once with the `init_merlean` skill; deps are pinned in `src/requirements.txt`.)

All commands — read-only queries and mutations alike — go through the CLI below. The store
lock is held only per call, so reads are safe from subagents.
`<DATA_DIR>` is the **data folder next to the target file** (`<file>_data/`, or `<lib>/datas/`
for a whole library). It holds the graph (`qdrant/` + `history.db`) plus the auto-written
`statements.json`, `progress.json`, and `analytics.json`. (`seed-sorries` derives `<DATA_DIR>`
from the file and prints it.) Output is JSON on stdout; the OpenAI key is read from `.env`
(or the `OPENAI_API_KEY` env var).
The data folder is git-ignored — nothing is stored inside the package.

## Commands
| Command | Use |
|---|---|
| `import-json PATH` | seed the graph from an existing `statements.json` (+ sibling progress/corrections) |
| `export-json [--out P]` | materialize `statements.json` + `progress.json` (debug / interop) |
| `list [--status S] [--kind K]` | all nodes (id/type/name/status/deps) — your overview. `--kind formal\|informal\|all` (default `all`); `--kind informal` reviews the banked notes |
| `get SID` | one node, full metadata (content, proof, anchor, deps, mathlib_types, status, …) |
| `topo` | statement ids in dependency order (deterministic) — the formalization order |
| `cone SID [SID...]` | forward (downstream) dependency cone — what to invalidate when SID changes |
| `cycles` | dependency cycles (must be `[]`) |
| `levels` | statements grouped by dependency layer (level 0 = no deps; same-level = independent) — the **parallel formalization schedule** (≤ 4 background compile-fix subagents at a time; see formalize/prove) |
| `set-status SID STATUS` | `pending` / `in_progress` / `completed` / `completed_axiom` / `failed` |
| `add --json '{"id":...}'` | add a node — a formal statement, or an informal Note (see "Informal notes") |
| `update SID --json '{...}'` | merge fields into a node (deps, content, anchor, corrections, …) |
| `delete SID` | remove a node |
| `sync-lean LIB_DIR` | **rewrite edges from the real `.lean` files** — run after every Lean change |
| `reconcile LIB_DIR [--build]` | **re-derive each node's `status` from its `.lean` file** (no `sorry` ⇒ `completed`, `axiom` ⇒ `completed_axiom`); self-heals the Mem0-g store's status drift. Prefer over trusting stored status; `--build` also requires `lake build` to pass |
| `lint` | **flag top-level decl names defined by >1 node** — a latent clash (ambiguous in any file importing both; a proof can bind the wrong one). Run after `sync-lean`; output `"n": 0` is clean |
| `seed-sorries FILE --lib-dir D` | prove mode: seed a file's `sorry`s (derives `--data` from FILE, prints it) |
| `record SID --role R --json '{}'` | append a subagent metric (tokens/tool_uses/duration_ms) to `analytics.json` |
| `status` | **readable progress dashboard** — counts, % done, per-statement status (the human view) |
| `analytics [--plain]` | `analytics.json` (`--plain` = readable per-statement token/time summary) |
| `summarize` | LLM narrative summary of the plan → `summary.md` + a searchable `Summary` meta-node (excluded from the graph/status) |
| `visualize [--lib-dir D] [--out P] [--format F]` | render the graph as a Graphviz diagram (default into `<DATA_DIR>`) |
| `search "QUERY" [--top-k N] [--retrieve-k K] [--no-rerank] [--kind K]` | semantic search — find nodes by MEANING. See "Semantic search" below. |
| `reset` | wipe the `<DATA_DIR>` folder |

## Node fields
`statement_id, type, name, content, dependencies[], dependents[], proof, anchor,
mathlib_types, lean_path, hierarchy_level, corrections[], status, do_not_import[],
declarations_defined[], imports[], source_start, source_end`.
- `status` replaces progress.json: a statement is "done" when `completed`/`completed_axiom`.
- `dependencies` is the source of truth for ordering and cone invalidation (node/file level).
- `declarations_defined`, `imports`, `source_start/end` are **derived by `sync-lean`** (recomputed
  every run) and kept in Mem0 — they're small and the dashboard/`lint` read them. `dependencies`
  stays the authoritative file-level edge set used for ordering/cones.

## Informal notes (`type: "Note"`)
A note is a **belief with evidence**, not a proven fact: an `explore` subagent's research
answer, a counterexample found, a dead proof approach, a measured threshold. Notes are
embedded for `search` (the `informal` group) but excluded from everything structural
(topo/levels/cone/status/export/sync-lean/lint). Canonical payload:
```
add --json '{"id": "Note_<Slug>", "type": "Note", "name": "<short title>",
  "content": "<the claim itself — this is what gets embedded; lead with the answer>",
  "confidence": "high|medium|low",
  "source": "explore: <topic> | orchestrator: during <node> | user",
  "evidence": "<short bullets>", "method": "<searches/experiments, params+seeds, tools+versions>",
  "caveats": "<what could overturn it>", "related": ["Thm_Main"]}'
```
Rules:
- **Only the orchestrator (main context) writes notes** — it curates what enters the store
  (subagents read; compile-fix's one mutation stays `sync-lean`).
- **`related`, never `dependencies`**: links to formal nodes are informational only. A formal
  node must NEVER list a Note in its `dependencies`.
- **On conflict, the note yields**: kernel-checked Lean results always beat notes. `update`
  the note (append the old belief + why it fell to `corrections`) or `delete` it. `add`/
  `update` stamp `created`/`updated` automatically.
- Notes get `status: "n/a"` and never appear in the dashboard or `statements.json`.

## Semantic search (`search`) — find nodes by MEANING, not exact name
Retrieval follows LeanSearch-v2's shape: an **embedding stage** (OpenAI) recalls candidates
over each node's informal+formal text, then an **LLM reranker** reorders them per group.
Rerank is on by default and matters — embedding order alone is often imperfect on short,
jargon-dense statements.
```
.venv/bin/python src/cli.py --data <DATA_DIR> \
    search "<natural-language query>" [--top-k N] [--retrieve-k K] [--no-rerank] [--kind K]
```
- `--top-k` (default 5) — results returned **per group**.
- `--retrieve-k` — embedding candidates to rerank (default `max(top_k*6, 30)`).
- `--no-rerank` — pure embedding similarity (faster, lower precision).
- `--kind formal|informal|all` (default `all`) — restrict to one group (skips the other
  group's rerank call).

Output is JSON with **two separately-ranked groups**:
```
{"formal":   [ {statement_id, name, type, status, embed_score, rerank_score, content}, ... ],
 "informal": [ { ...same fields..., confidence, source, updated}, ... ]}
```
`formal` = statement nodes (importable, citable as dependencies). `informal` = notes and the
plan summary — **beliefs with evidence, not proven facts**: use them as leads, never as
dependencies (see "Informal notes" above).

**When to search:**
- **Before adding any statement**: `search "<what the new lemma claims>"` — reuse an
  existing node instead of duplicating.
- **Before re-researching anything**: the `informal` group is the project's banked knowledge
  (prior explore answers, dead approaches, counterexamples) — check it before dispatching an
  `explore` subagent or re-deriving a conclusion.
- **Find the right lemma** to apply or depend on; **surface related statements** when
  decomposing or rephrasing.

Search notes: each store is small (one library/proof), so search is scoped to its
`<DATA_DIR>`. Embedding model `text-embedding-3-large` (3072 dims); reranker `gpt-4o-mini` (override
`PLAN_RERANK_MODEL`); key from `.env` / `OPENAI_API_KEY`. For exact-structure navigation
(order, status, cones) use `topo`/`list`/`get`/`cone` — search is for meaning, not structure.

## Common recipes
- **Next statement to formalize:** `topo`, then pick the first id whose `status` is `pending`
  and whose `dependencies` are all `completed`/`completed_axiom` (`get` each to check).
- **Mark done:** after a file builds clean AND passes its faithfulness check →
  `sync-lean LIB_DIR` (edges), then `reconcile LIB_DIR` (re-derive status from the files —
  self-healing). **Prefer `reconcile` over a bare `set-status SID completed`:** the Mem0-g store can
  silently revert a written status, and any later full-node write (even `sync-lean`) can lock the
  stale value in; deriving status from the `.lean` files is drift-proof. (`set-status SID in_progress`
  is still used to mark a node as being worked — `reconcile` leaves `sorry`-bearing files untouched.)
- **A statement changed (correction/rephrase):** `cone SID` → for each id in the cone,
  `set-status <id> pending` and delete its `.lean` file, so the loop re-formalizes the
  downstream cone. Then re-`sync-lean`.
- **After ANY plan edit:** run `cycles` (must be `[]`) and `sync-lean` so the stored graph
  never drifts from the Lean files, **then `visualize`** to regenerate `graph.png`/`graph.dot` so
  the picture always matches the just-updated `statements.json`. Run `lint` (after `sync-lean`)
  whenever you add helper nodes — it flags a top-level name accidentally owned by two nodes (a
  latent ambiguous-import clash) before it propagates.
