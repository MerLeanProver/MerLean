# MerLean

**Autonomous mathematics agents over a plan graph** — from an informal question to a
machine-checked Lean 4 + Mathlib result, and from a finished campaign to a publishable paper.

Give the research agent a paper, a stubbed `sorry`, or an informal open question. It decomposes
the goal into a dependency graph of lemmas, proves each node in its own file with a dedicated
`compile-fix` subagent, and drives the whole plan to a **sorry-free, axiom-clean** proof — one
whose `#print axioms` output is exactly `[propext, Classical.choice, Quot.sound]`, with no
`sorry` in the dependency cone. When speed matters more than certification, its **lite mode**
works NL-first — adversarial skeptic debate plus Python experiments — and fires Lean only at
the weakest links. When the mathematics is done, the paper-writing agent turns the campaign
into a paper through a gated 8-step protocol.

## Two agents × N runtimes

|  | **Claude Code** | **Codex** | *(future: opencode, …)* |
|---|---|---|---|
| **Research agent** — formalize / prove / auto-research / lite-research | [`.claude/`](.claude) (live at the repo root — the repo *is* the Claude Code install) | [`research-agent/codex/`](research-agent/codex) | one folder per runtime |
| **Paper-writing agent** — campaign → gated 8-step paper | [`paper-writing-agent/claude/`](paper-writing-agent/claude) (invoked via `/write-paper`) | [`paper-writing-agent/codex/`](paper-writing-agent/codex) | one folder per runtime |

Each version of an agent implements the same modes, roles, and artifacts; only the
orchestration is adapted to the runtime (Claude Code runs parallel background subagents;
Codex runs the same roles as child skills). Overviews:
[`research-agent/README.md`](research-agent/README.md) ·
[`paper-writing-agent/README.md`](paper-writing-agent/README.md).

The repo is **install-ready as checked out** for the Claude Code versions: `.claude/` (all
skills, subagents, settings) is tracked in git, and `src/` holds the plan-graph package. One
skill — `/init_merlean` — prepares the runtime.

---

## Quick start

**1. Clone the repo and enter it.**

```bash
git clone https://github.com/MerLeanProver/MerLean.git
cd MerLean
```

**2. Start Claude Code.**

```bash
claude
```

**3. Run the setup skill.**

```
/init_merlean
```

That one skill does everything: builds the shared `.venv` from `src/requirements.txt`, generates
`.mcp.json`, creates the root Lean workspace files if missing, and runs `lake update` +
`lake exe cache get` + `lake build`. Re-running it is safe — it is idempotent.

**4. Provide an OpenAI API key when it asks.**

> [!IMPORTANT]
> **An OpenAI API key is required.** `/init_merlean` will ask for one if it cannot already find
> a key, and store it in `.env` (git-ignored, never committed). Get one at
> [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
>
> **What it is for.** The plan graph. Every statement and research note is embedded
> (`text-embedding-3-large`) so the system can search its own plan by meaning — this is how it
> avoids re-proving lemmas it already has and how it recalls prior findings. A small model
> (`gpt-4o-mini`) handles the rest of the graph's bookkeeping: reranking search results,
> extracting memory facts, and writing plan summaries. The system cannot run without it.
>
> **What it costs — about $5 per month** of steady use. That is separate from, and far smaller
> than, your Claude Code subscription. Nearly all of it is the `gpt-4o-mini` calls; embedding a
> whole plan costs fractions of a cent.
>
> Every model is overridable: `PLAN_EMBED_MODEL`, `PLAN_LLM_MODEL`, `PLAN_RERANK_MODEL`,
> `PLAN_SUMMARY_MODEL`.

**5. Point it at an open question.**

```
/goal /auto-research <your open question> until it is fully resolved and formalized
```

MerLean will keep attacking the problem until it is resolved on its own, but we do recommend users to stop and discuss it with the agent. 
Also, we recommend user to use MerLean with other skills on math researches. 

---

## The three modes

| Skill | Input | What it does |
|---|---|---|
| **`/formalize`** | a paper (`.tex` / `.pdf`) | Extracts a dependency-ordered statement plan, then formalizes every node to verified Lean, with faithfulness and paper cross-checks. |
| **`/prove`** | a Lean file with `sorry` / `admit` | Decomposes each goal into helper lemmas and proves them node by node. Relentless: never stops early, never admits an axiom. |
| **`/auto-research`** | an informal open question | Formalizes the question into a Lean statement, then resolves it — **proving or disproving**, pivoting only on independently verified counter-evidence. Fully autonomous: ambiguous formalizations are decided by canonical reading and loudly documented. Races a portfolio of 2–3 genuinely different routes in parallel (including a disproof route when the direction is uncertain), killing and replacing dead ones. |
| **`/lite-research`** | an informal open question | **MerLean-lite** — the inverse verification budget: natural-language proof first, at speed. Races parallel *representation-hunting* routes, develops the best into a step ledger under adversarial skeptic debate and small Python experiments, then fires Lean **only at the triaged weakest links** (one contested step proved from its accepted priors as hypotheses). Graded **BRONZE** (debate+numerics) / **SILVER** (+ Lean-certified weak links) / **GOLD** (handed off to `/auto-research` for the full axiom-clean build). |

**Helper skills** — `/formalizeproblem` (informal problem → faithful Lean statement with `sorry`;
translation only, no proving), `/plan-graph` (inspect, edit, and semantically search the plan),
`/init_merlean` (set up the runtime), `/write-paper` (drive a finished campaign through the
paper-writing agent's 8-step protocol — see
[`paper-writing-agent/`](paper-writing-agent)).

**Worked examples** — [`examples/`](examples) holds complete campaign records, including a
deliberately small end-to-end demo (`lite-research` on an undergraduate linear-algebra fact,
run to a GOLD full formalization, plus the paper-writing run over it).

---

## How it works

**The plan graph** (`src/plan_store/`) is the system's memory. Each statement is one node;
dependency edges live in node metadata and are kept equal to the real Lean dependency graph by
`sync-lean`. The graph also stores **informal notes** — research conclusions with provenance (an
`explore` answer, a counterexample, a dead approach) — searchable alongside the formal statements
but excluded from the dependency graph and from export. Notes are revised or deleted when a
kernel-checked result contradicts them.

All access goes through one CLI:

```bash
.venv/bin/python src/cli.py --data <DATA_DIR> <command>
# Windows / Git Bash: .venv/Scripts/python.exe
```

**Skills run in the main context** — the orchestrator and all plan edits live there.

**Subagents run in separate contexts** and return only a short summary:

- `compile-fix` — iterates one Lean file until it compiles clean, without weakening the statement.
  Dispatched in the background, **up to 4 in parallel**, never two on the same file, each banked
  immediately on completion. This is *signature-locked parallelism*: a node's proof needs only its
  dependencies' signatures, so files are scaffolded early and proved concurrently.
- `explore` — researches a subtopic (web search, numerical experiments, tool downloads) and
  reports an evidence-backed answer. Read-only toward the repo.

**`.mcp.json`** (generated by `/init_merlean`) registers the `lean-lsp` MCP server, run from the
shared `.venv` via `python -m lean_lsp_mcp` — no `uv` required. Subagents fall back to `lake build`
if it is absent.

---

## Results

**The ACMAX conjecture** (Kolokolnikov, Conjecture 1.5,
[arXiv:1412.6147](https://arxiv.org/abs/1412.6147)) — among all simple graphs on `n` vertices with
exactly `2(n−2)` edges, algebraic connectivity is maximized by `K_{2,n−2}`, at exactly `2`.
Open in the mathematics literature when the campaign began, and now **proved for every `n ≥ 4`** —
`ACMax.acmax_conjecture`, axiom-clean, with no `sorry` anywhere in its dependency cone.

*(Separate repository — link to follow.)*

---

## Citation

If you use MerLean or build on this result, please cite:

```bibtex
@misc{ren2026merleanagenticframeworkautoformalization,
      title={MerLean: An Agentic Framework for Autoformalization in Quantum Computation}, 
      author={Yuanjie Ren and Jinzheng Li and Yidi Qi},
      year={2026},
      eprint={2602.16554},
      archivePrefix={arXiv},
      primaryClass={cs.LO},
      url={https://arxiv.org/abs/2602.16554}, 
}

@misc{li2026merleanproverrecursiveloopingharness,
      title={MerLean-Prover: A Recursive Looping Harness for Lean 4 Theorem Proving}, 
      author={Jinzheng Li and Zeru Zhu and Yuanjie Ren},
      year={2026},
      eprint={2605.26959},
      archivePrefix={arXiv},
      primaryClass={cs.LO},
      url={https://arxiv.org/abs/2605.26959}, 
}

@misc{zhu2026maximizingalgebraicconnectivity2n2,
      title={Maximizing Algebraic Connectivity with $2(n-2)$ Edges: The Large Vertex Number Case}, 
      author={Zeru Zhu and Jinzheng Li and Yuanjie Ren and Ji Liu},
      year={2026},
      eprint={2608.07360},
      archivePrefix={arXiv},
      primaryClass={math.CO},
      url={https://arxiv.org/abs/2608.07360}, 
}
```

---

## Layout

```
.claude/                  # RESEARCH AGENT, Claude Code version (live — the repo is the install)
  agents/                 #   compile-fix, explore, route-scout, nl-prover, skeptic
  skills/                 #   formalize, prove, auto-research, lite-research,
                          #   formalizeproblem, plan-graph, write-paper
    init_merlean/         #   setup skill: SKILL.md + setup.sh + templates/
  settings.json
src/
  cli.py                  # CLI launcher
  plan_store/             # the plan-graph package (store, lean_sync, search, tests, ...)
  requirements.txt        # pinned venv deps, incl. lean-lsp-mcp

research-agent/
  README.md               # the agent + its version matrix
  claude/                 #   pointer to .claude/ + src/ above
  codex/                  # RESEARCH AGENT, Codex version (standalone port + offline plan store)

paper-writing-agent/
  README.md               # the agent + its version matrix
  claude/AGENT.md         # PAPER-WRITING AGENT, Claude Code version (the 8-step protocol)
  codex/                  # PAPER-WRITING AGENT, Codex version (+ refine mode, paperctl)

examples/                 # complete campaign records (incl. the small LA demo + its paper)
refs/                     # verified arXiv TeX sources used by campaigns
AGENTS.md                 # conventions for agents working in this repo

# generated at install time by /init_merlean (git-ignored):
.venv/  .env  .mcp.json
lean-toolchain  lakefile.toml  MerLeanExperiment.lean  lake-manifest.json  .lake/
```

Secrets (`.env`, `*.key`), virtualenvs, Python caches, Lean build artifacts (`.lake/`), and
`.claude/` runtime state are git-ignored. Per-target plan data (`*_data/`) is **not** ignored — it
is committed alongside the campaign it belongs to, so a library ships with the plan graph, notes,
and verification scripts that produced it.

---

## Contributing

Issues and pull requests are welcome.


## Built on

Two projects shaped this one directly, and both are permissively licensed:

- **[Mem0](https://github.com/mem0ai/mem0)** (Apache-2.0) — the plan graph is a Mem0 2.x graph
  store: every statement and note is a memory node, and dependency edges live in node metadata.
  Used as a pinned dependency (`mem0ai==2.0.7`); no Mem0 source is vendored here.
- **[LeanSearch v2](https://github.com/frenzymath/LeanSearch-v2)** (Apache-2.0) — plan retrieval
  follows its two-stage shape, embedding recall then reranking, and the reranker instruction in
  `src/plan_store/rerank.py` is adapted from theirs. Modifications are described in `NOTICE`.

Also gratefully used: [Lean 4](https://lean-lang.org) and
[Mathlib](https://github.com/leanprover-community/mathlib4) (Apache-2.0),
[lean-lsp-mcp](https://github.com/oOo0oOo/lean-lsp-mcp), and
[Qdrant](https://github.com/qdrant/qdrant) as the vector store.

Helpers under `src/plan_store/_vendor/` are pure functions carried over from this project's own
predecessor plan store, not third-party code.

## License

Licensed under the **Apache License, Version 2.0** — see [`LICENSE`](LICENSE), with attribution
notices in [`NOTICE`](NOTICE).

Both upstream projects above are Apache-2.0, so this is a compatible relicense-free reuse: the
attribution and change-statement requirements of Apache §4 are satisfied by `NOTICE` and the
header of `src/plan_store/rerank.py`.
