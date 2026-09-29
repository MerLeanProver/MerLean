# Recursive paper writing

Internal compose/refine workflow of the existing Paper-writing agent. Inherit `<PLUGIN_ROOT>`
from its public entrypoint. Read `workflows/common.md`, the active provider adapter, and this
file completely. Use `scripts/paperctl` for deterministic state operations. This workflow
governs new schema-version-2 writing runs. Schema-version-1 saved runs retain the legacy
`paper-compose.md` and `paper/protocol.md` contract; do not reinterpret their gate passes.
Synthesis remains governed by `paper-synthesis.md` and needs no manuscript.

## Purpose and authority

Improve the presentation of an approved mathematical contribution. Assume the authoritative
source mathematics is correct; do not repeatedly reprove it, award a research grade, or
silently add a result. A writing PASS is not an independent correctness, novelty, or
publication certificate. Preserve conditional scope, credits, original evidence statuses,
source verification, claim identities, and required equivalence audits.

Use existing host subagent tools. There is no new model launcher, account/login operation,
background service, public specialist agent, or automatic research action. Preserve explicit
model choices and host capacity. Four independent checker roles can run in waves when only
three child slots exist. Read each role file before dispatch.

The coordinator alone changes authoritative state, the accepted manuscript, the shared
registry, and coverage/claim ledgers. A worker returns a patch or an independently attributable
artifact in its assigned output location. Reviewers never edit the manuscript or mark gates.
Do not start commits, installations, public release, or a new research campaign because a
review recommends them.

## 1. Establish the writing contract

Inspect the supplied run's mode and version before resuming. `resume` and `audit` are read-only:
neither dispatches workers nor refreshes a stale source. Snapshot Git status and preserve
pre-existing work. Initialization must preserve source bytes and exclusive output reservation.
If an authorized editor atomically replaces the output, investigate and use `claim-output`
before continuing; never claim an unexplained replacement.

Refinement initially copies the root manuscript, not a separately editable clone of every
included file. Candidate includes may still name the baseline's sections, macros, local
styles, bibliography, or assets. Before changing any shared dependency, make a private
candidate copy at a new path and repoint only the candidate's include/reference. Never edit
a shared baseline file: the complete source-closure drift guard deliberately blocks that
mutation even when the root source's bytes remain unchanged.

Record these durable inputs before drafting:

- The author-approved brief: audience, research question, contribution, one to four main
  results, scope, exclusions, and the desired presentation. One central result is sufficient.
- Immutable authoritative sources, their complete local dependencies, and original evidence
  statuses. Accept an approved synthesis handoff or author-approved notes; neither Lean nor
  a campaign is required. Refinement without separate notes uses the original manuscript as
  its mathematical baseline and explicitly records this limitation.
- Claim-to-source mappings for statements, all hypotheses and quantifiers, proof passages,
  dependencies, supporting results, and scope-limited summaries. Retain exact source text
  and hashes even when the new presentation uses equivalent wording.
- A notation/terminology registry and versioned, role-specific rubrics. Each checkpoint has a
  stable ID, purpose, acceptance condition, and required/advisory classification.

Use actual author approval evidence, not an agent-authored claim of approval. Conflicting
source versions, absent essential dependencies, or an unresolved choice of contribution
requires author direction. An approved synthesis already selects the angle: validate its
handoff and reuse verified sources; do not restart broad selection or novelty searching.
`CLEAR` still means no collision found within a documented search, not established novelty.

Read `paper/references.md` before adding or changing citations. Keep downloaded literature
and generated evidence in the run workspace, separate from immutable sources. Preserve
existing reference receipts and original proof/formalization grades without upgrading them.

## 2. Plan and write

Read `roles/paper-planner.md`. The planner maintains a compact external plan: outline,
contribution-to-section mapping, current objective, unresolved findings, repair decisions,
and source/claim constraints. Record it through `record-writing-plan`. Preserve older plans.
Pass the brief and focused artifacts, not the entire conversation, to each fresh invocation.

Read `roles/paper-writer.md`. Give the writer one consolidated objective plus the current
manuscript, relevant sources, registry, and applicable repair list. A whole-paper rewrite is
normal for an ordinary paper; do not mechanically split it into paragraphs or theorem-sized
tasks. Split only for document size, context volume, or difficult local reasoning, and retain
a later whole-paper consistency review.

The writer returns a base-revision-bound patch and an account of mathematical reformulations,
relocations, omissions, and source mappings. The coordinator checks the base, applies accepted
changes, and updates recoverable coverage records. Preserve originals for all omissions.
Do not mutate formal proof dependencies or source notes during a writing task.

Writing standards are reader-facing rather than compression quotas:

- Explain the main idea and important consequences sufficiently. Routine details may move
  to an appendix or verified citation, but not at the cost of a missing argument.
- Motivation, examples, limitations, and positioning are legitimate even outside a proof's
  ancestor closure. Record their purpose and evidence instead of deleting them automatically.
- Give each concept one authoritative definition before the relevant technical use. Informal
  previews and useful reminders are allowed. Do not enforce a fixed subsection distance.
- Prefer conventional, consistent notation and plain language. Domain conventions and the
  approved registry override generic glyph preferences.
- Display equations when long, referenced, or central enough to be clearer displayed; number
  when referenced or required by house style. Do not optimize for a blanket inline quota.
- Length statistics are informational. Expansion is acceptable when it improves understanding.
  No mandatory negative shrink or blanket byte-identity rule applies to this workflow.

Faithful reformulations are allowed only with preservation evidence. Existing main-result
locks, complete hypothesis surfaces, claim identities, recoverable coverage, and source hashes
remain binding. Where the preservation or synthesis contract requires two independent semantic
equivalence reviews, obtain them; a narrative or wording PASS is not a substitute.

## 3. Freeze a manuscript revision

Use `freeze-revision` only after the writer changes have been accepted. It freezes the complete
effective manuscript dependency set: root/included TeX, local macro/class/package files,
bibliography, figures, and other local assets. Relative manifest paths make snapshot hashes
independent of relocation. Missing dependencies or changes to immutable authority block review.

Do not edit a frozen revision. Do not write the next revision while reviews of the current
one are pending. Checkers inspect the snapshot, not an editable live file. Reserve disjoint
review-artifact locations. No reviewer has state-writing authority.

Five reviewed manuscript revisions are allowed by default, including the initial draft. Count
each once when review begins. Partial reviews, interruptions, and retries resume that same
revision; they do not consume a new one or reset the allowance. A rubric-only rerun is not a
new manuscript revision. If the fifth revision passes, finish. Otherwise pause before a sixth;
`continue-writing` records actual author authorization for an explicit extension, preserving
history. Neither ordinary resume nor a replanning pass extends the allowance.

## 4. Dispatch independent checkers

Run all four roles for every changed manuscript revision. No LLM checker selector is needed:

| Role | Read before dispatch | Main responsibility |
| --- | --- | --- |
| Faithfulness | `roles/paper-faithfulness.md` | Mathematical meaning, scope, evidence, dependency completeness |
| Narrative | `roles/paper-narrative.md` | Motivation, organization, transitions, explanatory emphasis |
| Notation | `roles/paper-notation.md` | Definitions, domains, conventional and consistent notation |
| Wording | `roles/paper-wording.md` | Plain language, stable terminology, redundancy, equation presentation |

Use `review-packet` to obtain the bound inputs. Each reviewer receives the frozen manuscript,
approved brief, its role/rubric, the relevant shared conventions, its own prior report and open
findings, and the changes since its own prior review. Additional evidence remains accessible
without filling the prompt with the entire project history. Do not supply peers' current
verdicts, a coordinator's preferred outcome, or a request to ratify a previous PASS.

The faithfulness packet additionally supplies authoritative sources and claim mappings. Its
first review is comprehensive. Later reviews use the cumulative diff from its last valid
PASS, not merely the preceding revision. Thus v1 PASS -> v2 FAIL -> v3 reviews v1-to-v3 plus
the unresolved v2 findings. Unchanged theorem text is not sufficient: changed macros,
definitions, assumptions, or proof dependencies may change its meaning. Major restructuring,
changed source authority, changed faithfulness requirements, or uncertain impact requires a
comprehensive review. Final coverage combines valid unchanged baseline coverage with reviewed
changes; never reuse an old PASS as if it certified a new manuscript.

Other checkers normally reread the whole paper. Prior findings and diffs guide attention;
they do not limit these roles to edited lines. Invoke an additional independent faithfulness
reviewer when existing two-review equivalence requirements apply. This is not a fifth permanent
checker, and the two invocations must have independent attributable identities.

Review reports must bind to the supplied receipt, manuscript, source contract, brief, registry,
rubric, role, and invocation. Findings have stable IDs, exact locations, evidence, severity
(required/advisory), and testable resolution conditions. A PASS cannot contain an unresolved
required finding. A blocker is an incomplete/blocked review, not a manufactured PASS.
Register returned evidence using `record-review`; retain the original independently produced
report and its digest, rather than editing it to fit the desired result.

## 5. Consolidate and recurse

Collect all scheduled feedback before replanning. One FAIL does not cancel the remaining
roles. A fundamental unreadable snapshot or unusable authority can interrupt the round;
record the reason and leave unfinished assignments incomplete.

The planner merges duplicate findings, resolves conflicting requests with evidence, and
records one consolidated repair plan. Track findings across revisions, including resolved
and reopened issues. Do not hide required repairs by renaming IDs, changing severity, or
deleting a report. Disputed findings need evidence-based reconsideration by the responsible
role, not a unilateral override of a required check.

Repeated or oscillating failures call for a specific diagnosis and revised plan, not history
reset or automatic relaxation of standards. A genuinely new theorem, stronger claim, new proof
route, source contradiction, or necessary change of paper angle pauses for author direction
and, if authorized separately, mathematical research/review. Writing is not that authorization.

Authors may extend checker rubrics without changing orchestration code. Version every change.
A changed rubric invalidates that role's certification and requires evaluating its new
requirements against the whole current manuscript. For rubric-only changes rerun affected
roles; manuscript changes require the normal four-role round. Reusing unchanged artifacts
must not bypass current requirements or reset the manuscript-revision allowance.

## 6. Complete or hand back an honest pause

Run protocol-aware `audit`, isolated `compile`, and final rendered-document inspection.
Compilation alone does not inspect clipped formulas, unreadable figures, poor page breaks,
or visual hierarchy. Bind the rendered inspection and build evidence to the current revision.
Never execute supplied source code as part of note intake; retain the existing isolated
no-shell-escape compilation discipline.

Completion requires four current role PASS reports for the same revision and applicable
contracts, no required open findings, all additional independent equivalence receipts where
needed, complete source/claim/reference/preservation evidence, isolated clean compilation,
and final visual inspection. Free-form gate prose and historical schema-1 passes cannot
replace these artifacts. Advisory improvements may remain clearly labeled.

If inputs, source scope, tool availability, or the revision allowance prevents completion,
leave a resumable checkpoint naming what is incomplete and what action is required. Never
claim success simply because work stopped. Report output/workspace paths, reviewed revision,
role verdicts, remaining limitations, source preservation, and next required author action.
Do not expand the contribution, draft another paper, commit, install packages, or publish as
an automatic consequence of this result.
