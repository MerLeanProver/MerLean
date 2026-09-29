# Research-to-paper synthesis

`synthesize` is a mode of MerLean's existing Paper-writing agent, not a fourth public agent or
an autonomous research launcher. It helps decide which coherent paper the available mathematics
can support **before** manuscript composition. It can also conclude that the material needs a
specific proof, a literature comparison, a better contribution, or no further action yet.

The workflow is:

```text
Notes -> claim inventory -> candidate prospectuses -> author selects an exact angle
      -> focused correctness and novelty reviews -> assessment and handoff -> STOP
```

The author-selection pause precedes focused novelty work. A drafting or research handoff is a
recommendation, not authority to execute that next activity. Correctness, novelty evidence, and
significance are separate assessments. A deterministic CLI pass establishes consistency of the
record, not mathematical truth, global novelty, or journal acceptance.

## Intake and commands

Supply LaTeX or Markdown notes. Linked Lean files, structured records, and experimental tables
may provide supporting evidence. Synthesis requires neither an existing campaign/DAG nor Lean
or a LaTeX toolchain. It does not execute source code or ingest PDF/OCR research notes. Choose
a run directory outside the MerLean repository, generated packages, and source-note directories.

```text
scripts/paperctl init-synthesize --source /project/notes.tex --source /project/results.md --work-dir /private/synthesis-run
```

`scripts/paperctl` is a POSIX shell wrapper. On native Windows, use the same Python CLI directly;
it does not require Bash, Lean, or LaTeX. For example, in PowerShell:

```powershell
$env:PYTHONPATH = 'C:\path\to\MerLean\src'
python3 -m paper_writing_codex.cli init-synthesize --source 'D:\project\notes.md' --work-dir 'D:\private\synthesis-run'
```

Replace the path with the installed package's `src` directory and retain any existing `PYTHONPATH`
entries when appropriate. Use your installed Python executable (`python` if `python3` is absent).
All later `paperctl` examples have the same `python3 -m paper_writing_codex.cli` equivalent.

Use the printed `RUN/state.json` path. Initialization passes the intake gate and snapshots the
explicit sources and discovered
local dependencies with hashes, and creates editable ledger/report templates. It does not reserve
a paper filename or create a TeX framework. Initialization does not interpret or prove the notes:
the coordinator reads them, populates the ledgers, and obtains independent reviews.

The six gates are `intake`, `inventory`, `candidates`, `selection`, `assessment`, and `decision`.
Use the existing deterministic gate command to validate a completed stage and bind its evidence:

```text
scripts/paperctl gate --state STATE --name inventory --status pass --evidence REPORT
scripts/paperctl resume --state STATE
scripts/paperctl audit --state STATE
```

`resume` and `audit` are read-only reports, not automatic continuations. They do not refresh source
snapshots, choose a candidate, modify gate status, or compile a paper. Audit-only mode also forbids
downloading new references. A failed or stale gate stays blocked until its cause is repaired.

## Run artifacts and evidence

The coordinator is the only writer of authoritative state and ledgers. Independent workers return
their own evidence files; the coordinator retains identities and hashes when consolidating them.
JSON records support validation; companion Markdown reports explain the mathematical reasoning.

| Artifact | Purpose |
| --- | --- |
| `input-inventory.json` | Explicit inputs, discovered dependencies, source hashes, and unresolved intake issues |
| `claim-ledger.json` | Exact statements, hypotheses, source locations, prerequisite claims, proof status, and unresolved issues |
| `candidate-prospectuses.json` | Alternative paper angles and a reasoned comparison |
| `selected-contribution.json` | Revision-bound approved contribution and its complete dependency closure |
| `reviews.json` | Independently attributable correctness and literature assessments of the frozen selection |
| `references-registry.json` | Source-checked literature evidence and citation records |
| `decision.json` | Terminal outcome, evidence, limitations, and an actionable drafting or research handoff |

Input snapshots, downloaded literature, and revision history remain separate. Do not modify the
source notes to make the inventory appear consistent, discard rejected candidates, or add private
research files to public test fixtures or packages.

The claim ledger separates conjectures and numerical observations from proof-bearing claims.
Retain every hypothesis, conditional scope, unresolved prerequisite, and existing grade. Neither
author approval nor independent prose review upgrades a research grade. Formal-verification claims
require their original evidence; absence of Lean does not preclude synthesis of informal proofs.

### Editable record contract

All JSON artifacts use `schema_version: 1`. Set `authored_by` in the claim and candidate ledgers
to the actual coordinator identity; the initialized blank value is deliberately not passing evidence.
`claim-ledger.json` contains a `claims` array whose records have:

- `id`, exact `statement`, `hypotheses`, `dependencies` (claim IDs), and `unresolved_assumptions`;
- `source_refs`, each with an inventoried `source_id` and precise `location`;
- `proof_status`: `conjecture`, `numerical`, `proof_available`, `independently_reviewed`, or
  `formally_verified`;
- `evidence`, a list of `{"path": "...", "sha256": "..."}` objects. Proof-bearing statuses
  require evidence. Paths must identify an inventoried source or a file inside the run;
- optional `grade_metadata`, preserved from original evidence rather than awarded by synthesis.

Use arrays of strings for hypotheses, dependencies, and unresolved assumptions, including empty
arrays where appropriate. Inventory may record missing or circular claim prerequisites, but a
selected candidate must have a complete acyclic closure. Its statement and hypotheses remain
separate frozen fields; neither can silently change during presentation.

A `formally_verified` claim additionally requires a `verification` object for readiness: `result`
equal to `pass`, `checked_at`, the executed `command`, hashed `evidence`, and `statement_sha256`.
The latter hashes the UTF-8 JSON object with keys `statement` and `hypotheses`, sorted keys,
`ensure_ascii=false`, and compact separators `,` and `:`. It binds the exact statement and premises;
the coordinator and independent reviewer must still verify what the original formal evidence proves.

A candidate contains `id`, `title`, `research_question`, `contribution`, `significance`,
`main_claim_ids`, `supporting_claim_ids`, `limitations`, `excluded_material`, and
`proposed_extensions`. Lists may be empty only when their meaning is genuinely empty. Main claims
contain one to four IDs for compatibility with composition; normally offer two or three candidates,
but one or no viable candidate is legitimate. Supporting proofs and prerequisites are not limited
by a main-theorem quota. Proposed extensions remain explicitly unproved until separately justified.

## Approval and assessment

After the candidate gate, present the prospectuses and recommendation to the author. The read-only
resume report supplies candidate digests. Capture a real author approval against the exact digest
and input revision; the approval JSON records:

```json
{
  "candidate_id": "candidate-a",
  "candidate_digest": "<current digest from resume>",
  "input_revision": 1,
  "author": "<actual approving author>",
  "approved_at": "<approval time>",
  "decision": "approve",
  "message": "<actual approval message for this candidate>"
}
```

This is a template, not evidence. Do not use placeholder values, an invented message, or an earlier
request to build/run the feature as approval of a mathematical contribution. The CLI checks the
record's fields and binding; it cannot authenticate a human or interpret their intent.

```text
scripts/paperctl select-synthesis --state STATE --candidate candidate-a --approval-evidence APPROVAL.json
```

Only now begin focused assessment of the approved contribution. Independent reviewers inspect its
exact statements, hypotheses, complete proof cone, and source evidence without receiving an intended
verdict. Correctness and literature review may run in parallel. Keep the reviewed revision, identities,
supporting evidence, and residuals explicit. A claim supported only by circular prerequisites, a
hidden assumption, numerical evidence, or an unsupported verification assertion cannot support
readiness as a proved theorem.

Use the [reference protocol](../workflows/paper/references.md) for substantive comparisons: inspect
primary source content, save local source and citation evidence, verify hashes, and record exact
claims. Search abstracts and snippets help discover sources but do not establish overlap. Store new
literature within the run's `refs/` directory, not immutable input snapshots. PDF restrictions on note
intake do not prevent inspection of authoritative primary literature PDFs.

Keep the existing novelty codes `CLEAR`, `ADJACENT`, and `COLLISION`. `CLEAR` means no collision
found within a documented search scope/date, not a proof of global novelty. `ADJACENT` needs an
explicit substantive difference. If the comparison is unresolved, say so and withhold readiness.
A known structural theorem can still support a paper through a significant new consequence;
likewise, many new examples do not by themselves establish a substantial contribution.

`reviews.json` contains exactly two `reviews` records, one with `kind: correctness` and one with
`kind: novelty`. Each records a distinct `reviewer` different from the ledger authors,
`candidate_digest`, `input_revision`, `verdict` (`pass`, `fail`, or `unresolved`), substantive
`findings`, and hashed local `evidence`. Identity fields permit consistency checks, not proof that
two identities actually represent independent reviews.

The correctness record's `covered_claim_ids` must equal the complete approved dependency closure.
The novelty record includes `search_scope`, `searched_at`, `reference_ids` (registry citation keys),
and `novelty_code`: `CLEAR`, `ADJACENT`, `COLLISION`, or `UNRESOLVED`. Registry records use the
existing reference-protocol fields. Reference sources, excerpts, citation snapshots, bibliography,
and arXiv extracted source directories must reside in `RUN/refs/`. A ready handoff needs both
reviews to pass and a `CLEAR` or scoped `ADJACENT` comparison backed by verified references.
The novelty review also records `references_sha256`, computed using
`synthesis.references_digest(STATE_PATH, reference_ids)` with a Python `Path` state argument.
This binds the verified reference records and bibliography bytes inspected by the reviewer.
Replacing a primary source and updating its registry hash does not preserve an old review's
validity. A new comparison is required; do not merely refresh the review hash without review.

Materially changing the contribution returns to author selection with fresh approval. Retain the
old assessment and do not automatically iterate through cosmetic reformulations or every rejected
candidate in search of a favorable verdict.

## Completion, recovery, and composition

The final report chooses a supported outcome: ready to draft, focused research needed, review or
verification needed, or no compelling paper identified. Record the reason, evidence, limitations,
and precise next step. A negative outcome may complete without fabricating approval or review
passes for inapplicable stages. An interrupted run awaiting selection is not a completed assessment.

In `decision.json`, set `outcome` to `ready_to_draft`, `focused_research_needed`,
`review_or_verification_needed`, or `no_compelling_paper`. Include `rationale`, `limitations`
and `next_steps` arrays, the approved `candidate_digest` (or `null` when unselected), and a
`not_applicable` object. Needs-work outcomes require actionable next steps.

An unselected `no_compelling_paper` outcome may finish after the first three gates if
`not_applicable` explains both `selection` and `assessment`. After approval, a non-ready decision
may explain an incomplete `assessment`; it cannot mark the already approved selection inapplicable.
The decision gate records these dispositions. Do not directly mark a gate `not_applicable` or
invent passing assessments. Readiness requires every gate and no inapplicable stages.

Audit the completed run using:

```text
scripts/paperctl audit --state STATE --require-all-gates
```

Source drift blocks stale decisions. Refresh is an explicit mutating operation, never a side effect
of audit or resume:

```text
scripts/paperctl refresh-synthesis --state STATE
```

Refresh archives the prior revision, snapshots the current explicit source closure, and reopens
extraction onward. Changes to the selected contribution invalidate its approval and assessments.
Do not hand-edit hashes or reuse stale approval to bypass this boundary.

For edits to an already passed ledger, prospectus, or review, **reopen before editing**:

```text
scripts/paperctl gate --state STATE --name assessment --status pending --evidence "Reopen to review new literature evidence."
```

Use `inventory` for claim edits, `candidates` for prospectus edits, and `assessment` for review or
reference edits. Reopening archives the old record and invalidates downstream gates. After editing,
repass applicable gates; changed claims or contribution require fresh actual author approval.
Changed reference evidence requires a new hash-bound novelty review, even after proper reopening.
Source-note edits use `refresh-synthesis` instead. Missing/corrupt old input snapshots block refresh;
source changes cannot legitimize damaged historical evidence. Linked/reparse input paths and
unsafe run aliases are rejected rather than followed during intake or revision.

Literal local TeX inputs, package/class files, and their nested local dependencies are included
in source snapshots and manuscript review hashes. Relative paths prefer the master document's
directory, with a containing-file fallback for standalone subfiles. Checks rediscover only the
explicit input closure, so a newly added local package or a file that changes path resolution also
requires refresh. Dependency discovery recognizes static, braced commands: it does not expand TeX macros, search external
`TEXINPUTS` directories, or inspect installed system packages/classes. Supply semantic dependencies
through literal local paths; the reviewers remain responsible for external toolchain context.

Directly editing passed artifacts and marking them passed again is rejected as receipt drift.
Immutable gate snapshots preserve prior passed records. Reopening after an accidental direct edit
does not recover any uncheckpointed prose already overwritten; retain ordinary backups as well.

After a separate request to draft, an eligible handoff initializes composition:

```text
scripts/paperctl init-compose --output /project/paper.tex --work-dir /private/paper-run --from-synthesis STATE
```

The handoff preserves approved claims, exact hypotheses, proof status, full dependencies, and
validated source evidence. It does not pass composition gates automatically or reopen broad paper
selection. One substantial central theorem is acceptable. Informal source proofs remain informal;
no Lean certificate is invented. Source notes remain untouched, and manuscript versioning and
preservation checks continue to apply.

### Freezing a source claim as a manuscript theorem

Composition keeps imported evidence and provenance under its work directory's `synthesis/`,
including `graph.json` for the full claim closure. Its `03-main-results.json` records each original
statement's raw UTF-8 `source_statement_sha256`, the `synthesis_candidate_digest`, and the full
`hypothesis_surface`. The new theorem's `normalized_sha256` is initially unset: importing an
informal statement is not permission to invent an equivalent TeX rendering.

After preparing the theorem environment, set its actual normalized statement hash. Even an exact
TeX match can omit separately recorded hypotheses or change meaning under different macros.
Retain two independent `source_equivalence_audits` for each imported main result, each with:

- `auditor`, `verdict` equal to `PASS`, and substantive `findings`;
- `candidate_digest`, `source_statement_sha256`, and `candidate_normalized_sha256`;
- `manuscript_sha256`, computed by `synthesis_bridge.manuscript_digest(inventory_tex(PAPER))`,
  binding the full manuscript source inventory, including macro/definition context;
- a local composition-workspace `evidence_file` and its `evidence_sha256`.

Reviewers must differ from the claim-ledger and prospectus authors. They check the exact source
statement, every hypothesis and quantifier, and the proposed
manuscript environment. Their hashes must identify the same source/selection and actual candidate
theorem. An old review of a different rendering cannot authorize a new one. These records establish
auditable semantic review, not formal proof equivalence or a research-grade upgrade. Composition
audits also recheck the live synthesis state and imported receipts; stale or invalidated readiness
blocks further use of the handoff.

## Evaluation and limitations

CLI regressions verify persistence, ordering, binding, source drift, recovery, negative completion,
and safe handoff. They do not evaluate mathematical taste or prove reviewer judgments. Keep a
separate human/agent evaluation of these synthetic scenarios:

| Scenario | Expected assessment behavior |
| --- | --- |
| All supported claims are already known | Report overlap; do not manufacture novelty by renaming them |
| A main argument has a fatal gap | Withhold readiness and identify the precise missing justification |
| Notes support two unrelated papers | Offer distinct prospectuses instead of forcing a single story |
| Source versions contradict one another | Expose the conflict rather than silently prefer the newest file |
| A known theorem has a substantial new consequence | Assess the consequence on its own merits and preserve credit |

Private pilots must pause for actual angle approval and keep unpublished notes, identities, and run
artifacts outside public fixtures. Version one does not autonomously prove gaps, choose journals,
predict acceptance, install plugins, commit, or publish. An assessment can be useful and complete
even when the correct recommendation is not to draft yet.
