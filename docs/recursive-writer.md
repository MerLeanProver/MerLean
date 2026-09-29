# Recursive paper writer

MerLean's existing Paper-writing agent now separates planning, writing, and four independent
editorial reviews. Its external state keeps long-running revisions resumable without asking
one model invocation to retain the entire research history or satisfy every constraint at once.

```text
Approved brief + source mathematics -> external writing plan -> proposed manuscript
    -> frozen revision -> faithfulness / narrative / notation / wording reviews
    -> consolidated repairs -> next revision, or completed writing assessment
```

All four checker roles review every changed manuscript revision. They run concurrently within
the host's capacity; a three-child host uses waves. The coordinator collects the full round
before replanning, rather than stopping at the first negative verdict. Ordinary papers receive
whole-paper tasks. Decomposition is available when length or complexity warrants it, not
required merely because the prover uses narrow tasks.

This workflow uses existing Codex/Claude host subagent tools. It does not start a separate model
launcher, manage accounts, add a public agent, or require a Lean campaign. The six existing
packages share one engine and the same writing contract.

## Start and resume

New compose/refine runs use schema version 2. Direct notes and an author-approved brief are
valid inputs; a previously approved synthesis handoff is optional.

```text
scripts/paperctl init-compose --output /project/paper.tex --work-dir /private/writing-run --source /project/notes.tex --brief /project/approved-brief.json
scripts/paperctl init-refine /project/paper-v1.tex --work-dir /private/refinement-run --brief /project/approved-brief.json
scripts/paperctl init-compose --output /project/paper.tex --work-dir /private/writing-run --from-synthesis /private/synthesis/state.json
```

Repeat `--source` for additional authoritative inputs. Refinement without separate notes uses
the original manuscript as its mathematical baseline and records that limitation. Source bytes
remain unchanged. Output versioning, exclusive reservation, and source-alias protections are
preserved. Use the state path printed by initialization rather than guessing it.

Refinement copies the root TeX file initially; included sections, macros, styles, bibliography,
and figures may still be shared with the baseline. Before editing a shared dependency, create
a private candidate copy and repoint the candidate include/reference. Do not edit the original
dependency. Source preservation covers the full dependency closure, not only the root's bytes.

When claim IDs are not yet known, omit `--brief` at initialization, inspect
`writer/source-claims.json`, and complete `writer/brief.json` before the first plan is recorded.
Initialization with a pending template is not permission to start drafting. The brief has this
shape; placeholders below are explanatory, not approval evidence:

```json
{
  "audience": "Researchers in the relevant mathematical field",
  "question": "The precise question this paper answers",
  "contribution": "The approved contribution, without proposed extensions",
  "scope": "The exact scope and conditional qualifications",
  "main_claim_ids": ["<ID from source-claims.json>"],
  "exclusions": ["Material explicitly outside this paper"],
  "approval_evidence": "<path to the actual author approval>"
}
```

One to four main claim IDs are accepted. Imported synthesis main claims cannot be replaced by
a new selection. An approval path may be absolute or relative to the run work directory. The
first registered plan freezes the brief and approval receipt. Do not edit that contract in
place afterward; a material change needs author direction and a newly approved run.

`scripts/paperctl` is a POSIX wrapper. On native Windows, set `PYTHONPATH` to the installed
package's `src` directory (preserving existing entries) and use
`python -m paper_writing_codex.cli` with the same arguments.

```text
scripts/paperctl resume --state STATE
scripts/paperctl audit --state STATE
```

Both commands are read-only. They report the next action and missing/stale evidence; they
do not dispatch agents, refresh sources, extend the revision limit, or write a gate PASS.
Saved schema-version-1 states retain their legacy eight-stage behavior. To use the new
workflow, create a new run rather than reinterpreting old passes. `--legacy-workflow` explicitly
selects the older contract when initializing a run.

## Coordinator operations and evidence

The coordinator is the sole writer of authoritative state, accepted manuscript, shared
registry, and claim/coverage records. Writers return base-bound patches; reviewers return
independently attributable artifacts in assigned locations. This is an orchestration and
receipt discipline, not an operating-system security boundary between agents with shared
filesystem access.

```text
scripts/paperctl record-writing-plan --state STATE --plan PLAN.json
scripts/paperctl freeze-revision --state STATE
scripts/paperctl review-packet --state STATE --role faithfulness --reviewer-id REVIEWER
scripts/paperctl record-review --state STATE --report REVIEW.json
```

`PLAN.json` records `planner_id`, `writer_id`, `base_revision` (`null` initially, then the
current ID such as `r001`), `objective`, `outline`, and `claim_map`. Map every source claim
exactly once with `claim_id`, `disposition` (`retained`, `cited`, or `archived`), `location`,
and `reason`. Main claims must be retained and have a `candidate_label` matching their body
theorem environment. Later plans add `repairs` entries containing `finding_id`, `action`, and
`reason` for every required finding. Set `full_faithfulness` when restructuring or uncertain
impact warrants comprehensive comparison. The coordinator supplies real invocation identities,
not reviewer names reused as author identities.

Use roles `faithfulness`, `narrative`, `notation`, and `wording`. Each packet supplies the frozen
manuscript, approved brief, applicable rubric and registry, that role's own previous report and
findings, and its changes. Reviewers do not receive peers' current verdicts or an intended
outcome. An additional independent faithfulness invocation supplies a second equivalence audit
where existing preservation/synthesis contracts require it; the other roles cannot substitute.

Reports identify `packet_id`, `reviewer_id`, `role`, `revision_id`, and the packet's exact
`bindings`, plus an evidence-based `summary`. Their verdict is `PASS`, `FAIL`, or `INCOMPLETE`.
`coverage` lists `checkpoint_id` entries, `PASS`/`FAIL` statuses, and evidence. Findings provide
stable `id`, `severity` (`required` or
`advisory`), `location`, `evidence`, and a testable `resolution`. `previous_findings` accounts
for previous IDs with objects containing `status` (`resolved`, `persisting`, or `regressed`)
and `evidence`. Faithfulness reports additionally copy the packet's `scope` and give a
`claim_reviews` entry for every source claim: `claim_id`, `status` (`faithful`, `inherited`,
or `unsupported`), and `evidence`. Comprehensive reviews cannot inherit claim coverage.
Use the packet's current schema and bindings; do not invent or manually refresh hashes to make
an old report match new material.

Disposition every required ID in the packet's `unresolved_findings`, not merely the last
report's findings. This list preserves unresolved branches from earlier invocations of the
same role/track. An unresolved item must remain a required finding in another failed report.
Layout reports follow the same rule. Current peer verdicts are not exposed; a second PASS
cannot silently override another independent invocation's unresolved failure.

Reports and approvals are evidence from actual invocations and author decisions, not documents
the coordinator may fabricate to satisfy a validator. Identity/hash checks detect inconsistent
records; they cannot prove that a human approved something or that two names represent genuinely
independent reviewers. The host must perform those independent invocations and preserve receipts.

Manuscript snapshots include root/included TeX, local packages/classes/macros, bibliography,
figures, and other literal local assets. Stable relative manifest paths make relocation harmless.
Discovery follows explicit references, not an indiscriminate repository scan, and executes no
supplied code. It is not a TeX interpreter: use relocatable literal paths for local dependencies;
dynamic/absolute dependency names need correction before safe snapshotting. Installed system
packages and external toolchain context are not copied and remain explicit build context.

## Review meaning, change handling, and stopping

Faithfulness assumes the approved source mathematics is correct. It checks meaning, hypotheses,
quantifiers, proof reasoning, dependencies, conditional scope, and original evidence status—not
a fresh proof or novelty claim. Necessary mathematical setup must be present or precisely cited
in the form actually used. A source contradiction or genuinely new argument requires author
direction and separately authorized mathematical review.

Its initial review is comprehensive. Later reviews use the cumulative diff since its last
valid PASS, not just the last edit. After v1 PASS, v2 FAIL, and v3 repair, it reviews v1-to-v3
plus unresolved v2 findings. Changes to standing assumptions or macros can alter unchanged
theorem text. Major restructuring, changed source authority, changed faithfulness requirements,
or uncertain impact calls for comprehensive review.

Narrative, notation, and wording normally review the entire current paper, using prior findings
and diffs to focus attention. Their role files contain stable default checkpoints (`F01`–`F08`,
`N01`–`N05`, `D01`–`D05`, and `W01`–`W06`). Required repairs block PASS; optional improvements
do not. The planner cannot dispose of a required finding merely by changing its severity.

Rubric additions are versioned. A rubric-only change invalidates that role's certification and
requires a fresh review of its new requirements across the current manuscript. It does not
consume another manuscript revision or reset the allowance. A manuscript edit schedules all
four roles. Historical reports remain preserved even when superseded.

New runs use default rubric version 4 (`defaults_version: 4`); `version` also tracks author
extensions. Rubrics without `defaults_version` keep the original version-1 acceptance baseline,
including saved rubrics whose author extensions already increased `version`. Validation retains
the exact required wording for saved version-1 and explicit version-2/version-3 baselines. Loading a
saved run does not migrate its state or rubrics. Current role-file hashes still bind reviews,
so a role update invalidates older
certifications even when the saved rubric bytes are unchanged.

Five reviewed manuscript revisions are allowed by default; configure `--max-review-rounds`
at initialization. The initial reviewed draft counts. Interrupted assignments and retries
resume the same revision. Revision five may complete successfully; otherwise the run pauses
before a sixth reviewed manuscript. Extend only with actual author authorization:

```text
scripts/paperctl continue-writing --state STATE --approval-evidence APPROVAL.json --additional-rounds 2
```

This adds an explicit allowance without discarding earlier reviews or pretending the run is
complete. Source uncertainty, a necessary scope change, repeated unexplained failures, or
unavailable build/rendered evidence can also produce an honest resumable pause.

Completion requires all four current role passes for the same revision and applicable
contracts, no required open findings, all additional equivalence receipts, valid source/claim/
reference preservation, isolated compilation, and rendered-document inspection. Use a `layout`
review packet/report for the final separately recorded rendered inspection. Free-form gate
prose cannot replace these artifacts. A clean compile does not detect clipped equations,
unreadable figures, or poor visual hierarchy.

```text
scripts/paperctl compile --state STATE
scripts/paperctl review-packet --state STATE --role layout --reviewer-id LAYOUT_REVIEWER
scripts/paperctl record-review --state STATE --report LAYOUT_REVIEW.json
scripts/paperctl audit --state STATE --require-all-gates
```

The layout packet uses `role: "wording"` and `review_kind: "layout"`; copy those fields and
the packet bindings into its report, record the inspected `pdf_sha256`, and account for every
page in `pages_inspected`. Inspect the retained build's PDF rather than a similarly named older
manuscript. A path-only `compile` remains an isolated diagnostic; `compile --state` records the
frozen revision's build evidence for completion.

Where two independent equivalence reviews are required, dispatch the second with
`--role faithfulness-secondary`. Its packet still has `role: "faithfulness"`, but
`review_track: "secondary"`; copy that field into the returned report. Primary and
secondary tracks receive their own prior feedback and must use distinct invocation
identities. One track's historical PASS cannot establish the other's coverage.

Each frozen revision records the coordinator's writer-task acceptance receipt: assigned
writer, base revision, plan, accepted manuscript hash, and computed changes. Include a
`mathematical_change_account` in the plan when accepting a writer's reformulation report;
retain the original returned worker artifact as supporting evidence. The acceptance receipt
does not claim that the writer performed an independent review.

## Editorial policy and delivery limits

The new path has no mandatory shrinking or blanket post-draft byte-identity rule. Faithful
statement/proof rewrites need preservation evidence; useful expansion is acceptable. Use one
authoritative definition with appropriate informal previews and reminders. Explain central
ideas adequately, keep routine detail proportionate, preserve necessary qualifications, and
prefer plain wording and stable terminology. Do not mechanically collapse distinct concepts
because their names look similar. Display formulas when long, referenced, or central enough
to benefit from display; number when referenced or house style requires it.

The version-2 defaults make these checks concrete: explain important nonstandard definitions'
interpretation and purpose before or immediately alongside their formal introduction; explain
supporting blocks before the technical detour; give each nontrivial numbered claim a visible
proof, precise citation, internal proof pointer, or identified deduction. A block can share one
introduction, and routine symbols need no motivation paragraph. Distinguish absent justification
from an existing proof that is difficult to find. Keep motivation and navigation in adjacent
prose where clearer without dropping formal scope. PASS coverage uses the existing evidence
fields for concise item-level locations and explanations, rather than global praise. Finding
severity still depends on concrete reader impact.

Version 3 strengthens N02, N03, and D01 without changing the faithfulness or wording checks.
Reviewers distinguish a definition's intended function from the conceptual reason for its
consequential non-obvious branches or terms. They inspect local blocks at changes of object or
argumentative purpose, checking ingredient roles and their connection rather than accepting a
generic announcement of tools. First-encounter evidence must come from the text available there:
later proofs, later applications, and reviewer reconstruction do not retroactively motivate an
introduction. Existing coverage fields record a short exact passage, its location, what it
explains, and whether any inference is immediate from local context or depends on later material.
Whole-paper review is retained; there is no new agent, review stage, or schema field.

Version 4 changes only N02. It distinguishes an ingredient's mathematical content from its
argumentative purpose. A short-inference justification must identify an already introduced
question or next-step objective, what the ingredient contributes, and their immediate connection.
Merely naming a calculation, bound, or count does not establish its use. At changes of object or
purpose, check why that family, comparison, or quantity appears here; later applications cannot
supply an objective that was not yet introduced. Missing orientation for a substantial block is
a required repair even if the mathematics and retrospective connection are elementary. Conversely,
an explicit goal and transparent connection suffice without another preamble. Routine steps in
a clearly directed proof are not separate detours. This refines an evidence test, not a new
workflow stage, schema field, or requirement for forward theorem references.

This standard does not demand boilerplate before every lemma or derivations of every constant.
Standard definitions, transparent cases, and short inferences from preceding mathematics may
already suffice. An unexplained central construction or substantial detour whose purpose must
be discovered later is a required repair; optional clarity beyond locally recoverable orientation is
advisory. Calibrate this distinction with matched editorial defects and controls, separately from
deterministic receipt tests. A blinded rerun on a manuscript that motivated rubric development is
a regression exercise, not a held-out benchmark or proof of general detection reliability.

Use author feedback through the existing inputs: a reusable editorial standard belongs in a
versioned rubric extension, a manuscript-specific repair belongs in the writing objective or
repair list, and a change of contribution or source authority follows the approved-contract
procedure. For a blind editorial regression, give fresh independent reviewers the frozen
manuscript, approved brief, source mappings, registry, role, and rubric through ordinary review
packets; withhold retrospective author findings and expected verdicts. Compare the returned
reports with that feedback afterward. This uses the existing workflow and report fields.

These freedoms do not weaken frozen main-result identities, hypotheses, grades, reference
verification, recoverable coverage, or two-independent-review requirements. New research,
changed contribution scope, commits, plugin installation, synchronization, and publication
remain separately authorized actions.

Deterministic tests evaluate receipt consistency, source protection, resumption, stale-review
rejection, limits, and legacy compatibility. Actual archived reviewer evaluations separately
test editorial judgment using planted defects and matched positive controls. Passing schema
tests alone does not demonstrate mathematical or editorial quality. Keep private pilot notes,
findings, paths, and run artifacts outside public fixtures and generated packages.

The maintained workflow is `workflows/paper-recursive-writing.md`; internal planner, writer,
and checker contracts are in `roles/paper-*.md`. A finished run is a writing assessment under
its source assumptions—not a correctness certificate, proof of novelty, or promise of acceptance.
