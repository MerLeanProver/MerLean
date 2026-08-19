# MerLEAN graph routing

Prefer an existing graph/export.

## Plan export

`<project>/FermionGaussian_data/statements.json`-style exports contain
`{statements:[{id,type,name,content,dependencies,...}]}`. Dependencies point from each node to its
prerequisites. Pass selected terminal IDs explicitly:

```text
paperctl critical-path statements.json --select Thm_PaperRoot --out 01-critical-path.md
```

## Dependency-browser graph

From the campaign's plan-store repository root, the SDK-free commands are:

```text
.venv/bin/python -m autoinformalization.cli graph LIB --candidates
.venv/bin/python -m autoinformalization.cli graph LIB --select id1,id2
```

They write `LIB/dependency-graph/graph.json`. Its edges are dependency → dependent and its
`critical_path_node_ids` field is the ancestor closure, not a single longest path. `paperctl
critical-path` verifies acyclicity and returns all tied deepest paths up to its safety cap.

Do not generically parse `graph.dot`: some projects display the reverse orientation. The Mem0-g
store is single-writer; never query/mutate it concurrently. Manual main-result selection is required:
the automatic ending-boundary heuristic can select plumbing.

Graph metadata does not certify theorem grade or hypotheses. Verify those against actual source,
certificate audit, and `#print axioms` evidence, and record the provenance in `01-critical-path.md`.
