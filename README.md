# MerLean

Three mathematics agents, available in **Claude Code and Codex**: six entrypoints in total.

| Agent | When to use it | Verification target |
| --- | --- | --- |
| **MerLean -lite** | Explore a question, develop a natural-language proof, debate it, and Lean-check its weakest links | **SILVER** |
| **MerLean -heavy** | Fully prove a result, formalize an existing proof or paper, or complete Lean proofs | **GOLD** |
| **Paper-writing** | Compose, refine, resume, or audit a mathematics paper | Preserve the recorded research grade |

**Lite is on by default.** Bare MerLean selects Lite; `-heavy` is the explicit name for
the former “Lite off” state. The flags are mutually exclusive. Silver and Gold are evidence
thresholds, not labels awarded automatically: unfinished Lite work may remain Bronze, and
Heavy cannot report Gold until its full audit passes. Lite does not silently escalate to Heavy.

## Choose a workflow

- “MerLean: investigate this question” → Lite.
- “MerLean -lite: check this proposed proof” → Lite, even though a proof is attached.
- “MerLean -heavy: finish this result to Gold” → Heavy.
- “Formalize this natural-language proof/paper in Lean” → Heavy, using the supplied proof.
- “Fill the sorries in this Lean file” → Heavy, preserving its statements.
- “Translate only this statement; do not prove it” → Heavy's scoped translation procedure,
  with an **unproved** output and no research grade.
- “Write/refine/audit this paper” → Paper-writing. Audit-only remains read-only.

There is no separate public formalization agent. Heavy contains the paper-formalization,
Lean-proof completion, statement-translation, and open-question procedures. An existing proof
can eliminate proof-discovery work; it does **not** eliminate the work of faithfully encoding
objects, filling missing lemmas, auditing citations, and checking the entire Lean dependency cone.

## Install from the plugin marketplaces

Both provider catalogs are published in this repository: Codex reads
`.agents/plugins/marketplace.json`, and Claude Code reads
`.claude-plugin/marketplace.json`. Each catalog exposes three standalone packages.
The marketplace name remains `merlean`.

For Claude Code, add this repository as a marketplace:

~~~text
/plugin marketplace add MerLeanProver/MerLean
/plugin install merlean-lite-claude@merlean
/plugin install merlean-heavy-claude@merlean
/plugin install paper-writing-claude@merlean
~~~

For Codex, add this GitHub repository as a plugin marketplace through the host's
marketplace interface, then select `merlean-lite-codex`, `merlean-heavy-codex`, or
`paper-writing-codex`. Installation and model access are handled by the host.

Version 2.0.0 replaces the former `merlean` Claude package and `lite-codex` Codex
package with explicit Lite/Heavy packages. See the [migration guide](docs/plugin-migration.md)
before switching an existing installation. `paper-writing-codex` retains its identity.

## Local use

Generate the six standalone packages:

~~~bash
python3 scripts/build_bundles.py
~~~

The generated packages are:

| Claude Code | Codex |
| --- | --- |
| `plugins/merlean-lite-claude/` | `plugins/merlean-lite-codex/` |
| `plugins/merlean-heavy-claude/` | `plugins/merlean-heavy-codex/` |
| `plugins/paper-writing-claude/` | `plugins/paper-writing-codex/` |

Each has exactly one public `skills/<agent>/SKILL.md`, its provider manifest, and all its
runtime/supporting files. They do not depend on symlinks or files outside the installed package.
Use a generated package with the host's local-plugin loading mechanism, or explicitly direct
an agent to read its entrypoint. **Building is not installation** and does not alter your
Codex/Claude configuration. The six directories are generated and included in public release commits; edit the
maintained source, never their copies. Rebuilding refuses locally modified or unknown files.

Catalog-based discovery is also retained: `python3 scripts/build_bundles.py --catalogs`
optionally generates local Claude/Codex marketplace catalogs, each with three entries.
This only creates repository-local artifacts; it does not register a marketplace, install
plugins, modify personal catalogs, or publish anything. Existing differing catalogs are preserved.

For a deterministic selection without calling any model:

~~~bash
scripts/merlean-agent
scripts/merlean-agent -lite --provider claude
scripts/merlean-agent -heavy --provider codex
scripts/merlean-agent --task formalize
scripts/merlean-agent --task translate-only
scripts/merlean-agent --paper-writing
~~~

This selector reports the entrypoint and target grade; it does not launch an LLM, install a
plugin, write campaign state, or award a grade. An explicit `--resume-mode heavy` preserves
the selected campaign mode. Omitted flags never inspect unrelated old campaign state.

### Runtime setup and tools

~~~bash
bash scripts/setup.sh --project /absolute/path/to/your/Lean-project
PLAN_OFFLINE=1 scripts/merlean --data /absolute/path/to/plan-data status
scripts/paperctl --help
~~~

Setup preserves existing project files and supports `--skip-venv` / `--skip-mathlib`.
For a read-only plugin installation, pass `--runtime /writable/runtime` and set the same
`MERLEAN_RUNTIME` for later plan commands. Keep projects and runtime directories outside
generated bundles so they remain rebuildable.

Offline graph operations are deterministic and credential-free. Online semantic search
retains the Mem0-g/vector-store backend and model overrides (`PLAN_EMBED_MODEL`,
`PLAN_LLM_MODEL`, `PLAN_RERANK_MODEL`, `PLAN_SUMMARY_MODEL`). Configure `OPENAI_API_KEY`
only through your environment or a local ignored `.env`; never paste keys into chat.
Python dependencies remain pinned in `src/requirements.txt`.

Setup can create a project Lean-LSP MCP descriptor. Host registration differs: a project
`.mcp.json` alone does not automatically register a Codex MCP server. The provider adapters
explain this boundary; Lean CLI/build verification remains available without MCP.

## What Gold means

Gold applies to the **exact frozen theorem**, not to every claim surrounding it. It requires:

- a clean Lean build and root-axiom/dependency-cone checks;
- faithful statements, explicit premises, actual intended objects/adapters, and no circular
  definitions or toy-model substitutions;
- complete theorem-face and goal-alignment audits;
- hashed evidence, independent audits, and a successful live Lean-backed grade audit.

A conditional theorem can be Gold: **if its explicitly named conditions hold, then its
conclusion follows**. That does not establish the conditions or solve an unconditional question.

A literature boundary is a last-resort **cost-dependent** decision: the result must be
standard/well supported, absent from the pinned Mathlib after concrete search, and
disproportionately costly to formalize after documented alternative attempts. Its exact
primary source must be stored locally under `ref/` or `refs/`, matched clause by clause,
and independently audited twice. Cost does not excuse a mismatched source or a new assumption.
Gold source boundaries remain explicit proposition binders, not new Lean `axiom` declarations.

See [the trust and instantiation gates](docs/trust-and-instantiation-gates.md).
Both providers use the **same executable grade engine**. Lite cannot call the Gold recorder.
Paper-writing preserves conditions, grades, source evidence, and the distinction between a
proved implication and an answer to an open question.

## Preserved capabilities

The simpler public interface retains plan-graph search and memory, deterministic offline
operations, initialization, representation scouting, natural-language proof ledgers, adversarial
skeptic audits, targeted Lean certificates, full proof/formalization, failure logs, and resume.

Heavy retains signature-locked parallel proof workers and full transitive certification.
GPT research/paper agents and their GPT workers default to **gpt-6-astra**; explicit choices
and Claude model settings are preserved. Explicit model-capacity failures retry every 10 seconds,
while API rate limits retain their existing wait/backoff behavior. These are live-agent dispatch
rules, not a mechanism to restart a host-level main-model failure.

Paper-writing retains the eight-stage protocol, new-paper composition, non-destructive
`-vN` refinement, resume, main-result locks, coverage ledgers, compression and appendix checks,
safe reference-source extraction, bibliography verification, isolated compilation, and read-only
audits. The same deterministic paper tools are now available to both providers.

## Maintained layout

~~~text
workflows/
  merlean-lite.md       public Lite entry template
  merlean-heavy.md      public Heavy entry template
  paper-writing.md      public paper entry template
  common.md            shared policy and mode/grade contract
  *.md, paper/         internal procedures and paper references
ports/                 Claude and Codex adapters
roles/                 internal specialist instructions
src/                   one plan/grade/paper implementation
scripts/               setup, CLI wrappers, generation and auditing
templates/             safe environment and Lean starter templates
tests/                 regression, semantic, routing and bundle tests
docs/                  strict trust boundary and migration notes
examples/              small retained demonstration
plugins/               generated six packages, committed for marketplace installation
~~~

The former `.claude/`, root `skills/` and `agents/`, `research-agent/`, and
`paper-writing-agent/` maintained copies are replaced by this shared source. Internal roles
are not extra user-facing agents. The public tree includes only the small demo under `examples/`; research campaigns,
private session records, credentials, and runtime caches do not belong in distributions.

## Verification and packaging

~~~bash
python3 -m unittest discover -s tests
python3 scripts/audit_research_runtime_parity.py
python3 scripts/audit_codex_release.py
python3 scripts/build_bundles.py --archives dist
~~~

The archive auditor covers both providers despite its historical filename. It rejects unsafe
paths, secrets, missing runtime files, extra public skills, broken package references, and
false-Gold acceptance. For reproducible committed releases, use
`python3 scripts/build_codex_release.py --treeish <commit> --out dist`; this compatibility
command now generates all six bundles from that Git tree. Publish only audited committed source and deterministic packages, with explicit
authorization for remote updates.

Archive creation refuses existing differing ZIPs and symlinks; choose a fresh output
directory for a changed release. Retained examples are historical demonstrations, not
newly recertified claims under the current Heavy gates.

Authorship and licensing are retained in [NOTICE](NOTICE) and [LICENSE](LICENSE).
Privacy, terms and security: [PRIVACY](PRIVACY.md), [TERMS](TERMS.md), [SECURITY](SECURITY.md).

## Citation

~~~bibtex
@misc{ren2026merleanagenticframeworkautoformalization,
  title={MerLean: An Agentic Framework for Autoformalization in Quantum Computation},
  author={Yuanjie Ren and Jinzheng Li and Yidi Qi},
  year={2026},
  eprint={2602.16554},
  archivePrefix={arXiv},
  primaryClass={cs.LO},
  url={https://arxiv.org/abs/2602.16554}
}
@misc{li2026merleanproverrecursiveloopingharness,
  title={MerLean-Prover: A Recursive Looping Harness for Lean 4 Theorem Proving},
  author={Jinzheng Li and Zeru Zhu and Yuanjie Ren},
  year={2026},
  eprint={2605.26959},
  archivePrefix={arXiv},
  primaryClass={cs.LO},
  url={https://arxiv.org/abs/2605.26959}
}
@misc{zhu2026maximizingalgebraicconnectivity2n2,
  title={Maximizing Algebraic Connectivity with $2(n-2)$ Edges: The Large Vertex Number Case},
  author={Zeru Zhu and Jinzheng Li and Yuanjie Ren and Ji Liu},
  year={2026},
  eprint={2608.07360},
  archivePrefix={arXiv},
  primaryClass={math.CO},
  url={https://arxiv.org/abs/2608.07360}
}
~~~
