# MerLEAN for Codex

This is the standalone Codex-native port of the MerLEAN Claude agent at the parent repository's
2026-08-17 HEAD. It preserves all workflow modes and specialist roles while adapting orchestration
to Codex skills and shared-workspace subagents.

## Modes

- `init-merlean`: prepare the Python, lean-lsp, and optional Mathlib runtime. This is Codex's
  normalized spelling of the upstream Claude command `init_merlean`.
- `formalize`: paper to a fully verified Lean library.
- `prove`: recursively eliminate every `sorry` or `admit` in an existing Lean file.
- `auto-research`: settle an informal question by proof or verified disproof.
- `formalizeproblem`: translation-only informal mathematics to type-checking Lean statements.
- `lite-research`: natural-language route portfolio, skeptic debate, experiments, and targeted
  Lean certificates.
- `plan-graph`: inspect and semantically search formal nodes and research notes.

Specialist skills `compile-fix`, `explore`, `route-scout`, `nl-prover`, and `skeptic` are designed
for orchestrator-spawned subagents but can also be invoked directly.

## Runtime

Run the `init-merlean` skill, or execute:

```bash
bash skills/init-merlean/scripts/setup.sh
```

The plan CLI is then:

```bash
scripts/merlean --data <DATA_DIR> <command>
```

An OpenAI API key is required only for the default online Mem0-g embeddings and reranking. Lean
verification requires `lake` on `PATH`. The plugin is Apache-2.0 licensed; see `LICENSE` and
`NOTICE`.

The online Mem0-g backend remains the default. If embeddings or LLM calls are unavailable, select
the deterministic local fallback explicitly:

```bash
PLAN_OFFLINE=1 scripts/merlean --data <DATA_DIR> <command>
```

Offline mode supports the same commands, persists its authority in
`<DATA_DIR>/.merlean-offline.json`, and still materializes `statements.json`, `progress.json`, and
`analytics.json`. Search uses documented weighted lexical matching (query coverage, token Jaccard,
and an exact-phrase bonus) with stable insertion-order tie breaking; `embed_score` carries that
lexical score for output compatibility. Summaries are deterministic plan/status reports. No
embedding, vector-store, reranker, or summary API call is made in this mode.

When switching an existing online plan to offline mode, formal nodes can be recovered from the
materialized `statements.json`/`progress.json` views. Online-only `Note` and `Summary` meta-nodes
are not present in those views, so export or recreate them explicitly if they must cross backends.
