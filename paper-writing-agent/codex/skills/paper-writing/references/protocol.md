# Gated paper protocol

## Artifacts and gates

### 0. Preflight and baseline lock

Create `00-run-state.json`. In refine mode also create `00-baseline-inventory.json`,
`00-baseline-source.sha256`, `00-main-results-lock.json`, and both JSON/Markdown coverage ledgers.
Inventory sections, statements including unlabeled ones, definitions/notation, displays, proofs,
figures/tables, citations, footnotes, includes, and substantive prose. Freeze each baseline main
result's exact environment, label, statement, hypotheses, quantifiers, constants, scope, and
conclusion. Gate: source hash frozen, output exclusive and absent before initialization, source and
output are not aliases.

The output inode is reserved. If a legitimate editor uses an atomic save, adopt the new regular,
single-link inode with `paperctl claim-output --state WORK/00-run-state.json` before continuing;
never claim an unexplained replacement.

### 1. Critical path

Deliver `01-critical-path.md`: theorem-grade DAG, separate defense artifacts, all tied deepest paths
to selected terminals, one-line statements, grades, and full terminal hypothesis surfaces. Record
the edge source: Mem0-g, dependency-browser JSON, certificate embeds/axioms, or ledger delivery.
For every selected result, also record its full ancestor closure and induced formal edges; longest
paths are navigation aids, not substitutes for the dependency cone. Freeze the graph hash and both
the dependency and reverse-consumer maps. Gate: verify grades and hypotheses against actual
certificate/audit files.

### 2. Empty framework

Deliver compilable `02-framework.tex`: Introduction; Preliminaries/Setup; one mathematics-named
section per result cluster; Verification; Outlook; appendices; References. In refine mode add a map
from every baseline section/topic to its planned destination. Gate: isolated clean compile and no
orphaned baseline topic.

### 3. Main results, novelty, theme

Choose 2–4 strongest, deepest results forming one through-line. Reuse a dated novelty record, then
search arXiv from that date through today. Confirm closest hits and inspect source TeX, not search
snippets. Record `CLEAR`, scoped `ADJACENT` with a delta sentence, or `COLLISION`. Decide a
field-standard title and three-sentence theme. Deliver `03-main-results.md`. In compose mode also
lock each result in `03-main-results.json` with its graph node, body label, normalized statement
hash, complete hypothesis surface, `CLEAR`/`ADJACENT` novelty status, and evidence. Gate: no unresolved
collision and one-sentence through-line. In refine mode the main-result lock cannot be demoted.

### 4. Proof-dependency presentation and supporting lemmas

Work only in Lean and Markdown during this stage; do not edit candidate or paper TeX. Use the full
selected-result ancestor cone in `01-critical-path.md` as the frozen formal DAG and `04-lemmas.md`
as the reader-facing dependency plan and recovery ledger.

Give every considered node one action: `KEEP`, `SPECIALIZATION_OF`, `INLINE`, `OMIT_ELEMENTARY`,
`OFF_PATH_SUMMARY`, or `OFF_PATH_LEDGER_ONLY`. Record its formal ID and source, normalized statement,
formal dependencies and consumers, presentation dependencies and paper consumers, replacements,
rationale, and recovery anchor. A direct specialization may be collapsed only when a placeholder-
free Lean witness proves it by explicit instantiation of the retained general result without another
theorem-grade ingredient. Selected and locked results are always `KEEP`.

Map every old live paper consumer of a collapsed or omitted unit to a surviving replacement, then
recompute the reverse presentation-consumer map. Formal edges remain frozen. If an explicitly
authorized Lean edit changes them, invalidate this and every later gate, rebuild Lean, regenerate
the formal graph, and record the old/new edges before continuing. Gate: the full cone is covered,
the presentation DAG is acyclic, every consumer resolves, every omission is recoverable, every
specialization witness compiles without placeholders or new axioms, and no TeX changed in this
stage.

### 5. Organize and draft

Draft only the new/versioned TeX, plus appendix and bibliography files if split. Census explicit
and prose definitions, standing constraints, macro/declaration commands, and notation. Introduce
each exactly once, immediately before first technical use in expanded document order, with no
unrelated theorem between. A notion shared across sections, source files, or body and appendix has
one authoritative occurrence in the root main TeX. Cite textbook/published steps. Put technical and
lengthy work in appendices. Factor shared notions only when strength is unchanged. Maintain the
reference registry. Gate: definition census, coverage ledger, citations, summary-strength SOL
audit, and isolated clean compilation all pass.

### 5.5. Compression and shrink gate

After the complete draft passes, run `paperctl freeze-shrink --state WORK/00-run-state.json`.
This compiles the draft and freezes the pre-shrink TeX inventory, bytes, and page count. Then classify
every mathematical unit:

- `CORE_INLINE`: original/significant mathematics kept in the body.
- `IMPORTANT_BODY_APPENDIX`: important routine statement stays in the body; proof moves.
- `CITED`: standard/published result stated as needed and cited, without reproof.
- `LEDGER_ONLY`: elementary, redundant, boring, and unnecessary for the reader; remove from TeX but
  preserve the verbatim raw TeX (including comments and formatting), normalized statement and both
  hashes, source, old/new consumers, and rationale in
  `05.5-deleted-steps.md`.
- `AUDITED_STYLE`: a frozen proof whose presentation is rewritten without changing its mathematics.
  Record the replacement proof label or unit id, source, consumer, rationale, and two independent
  semantic `PASS` audits. Never apply this class to a theorem-like statement.

Never classify a main result, scope condition, caveat, consumed definition, or required logical
interface as `LEDGER_ONLY`. For `IMPORTANT_BODY_APPENDIX`, preserve the body statement and stable
label; add a body reference to the appendix proof; give that proof a unique label and a back-reference
to the body statement. The shrink pass may move/delete proofs or whole classified routine units, but
every surviving theorem/lemma/proposition/corollary statement must remain byte-identical to the
frozen full draft. Gate: machine ledger complete, all live consumers replaced, both directions
resolve, and the Markdown archive is substantive rather than a vague note. Report net shrink but do
not delete merely to hit a target. Rerun the compression inventory if post-draft mathematical
material is added. Use `paperctl shrink-stats --state ...`; it compiles again and writes the
byte/unit/page and main-text delta to `05.5-shrink-report.json`. The main-text delta must be negative;
if no safe shrink is possible, fail the gate rather than delete mathematics merely to hit a target.

When a direct specialization is removed, retain the general result as its target, archive the exact
specialized statement and Lean witness, and record complete old consumers, new consumers, and their
mapping. Every old live consumer must resolve to the retained result or another surviving unit.

### 6. Final matter

Write the abstract last (at most 200 words): through-line, main results at weaker-or-equal strength,
and one honest verification clause. Confirm title. State outlook items as questions with what is
known and provenance. Gate: abstract and section summaries pass a theorem-by-theorem strength audit.

### 7. Terminology, notation, and layout

Deliver `07-terminology.md`: concept, one field-standard term, one notation, rejected synonyms, and
collision checks. Replace synonyms, avoid invented nouns unless explicitly introduced, and resolve
one-symbol/two-object or two-symbol/one-object conflicts. Gate: grep and semantic SOL audits find no
unresolved synonym or notation collision.

Only after the proof plan, Lean build, compression, definition census, and terminology checks pass,
freeze a pre-layout inventory and apply layout as a presentation-only pass. Preserve a supplied
journal class; otherwise use a standard mathematics-journal class with approximately `0.85in`
margins and never less than `0.75in`. The pass may change only the class and ordinary geometry,
font, header/footer, and float settings. It may not change mathematical units, declarations,
definitions, notation, labels, references, citations, or includes, and it may not use tiny type,
condensed line spacing, negative spacing, scaling, cropping, or forced overlap.

### 8. Release

Recheck the baseline hash. Complete every coverage disposition. Audit locked main results. Verify all
reference-source/BibTeX records. Compile clean in isolation. Obtain two independent SOL PASS verdicts.
Make path-scoped local checkpoints only; never push. Report title, main results, reference count,
pages, open items, output path, and baseline hash.

After each earlier gate passes, make its path-scoped local checkpoint before opening the next gate
when the project is a Git worktree. At release, update the campaign dossier's repair-record appendix
with “paper vN drafted,” then make the final path-scoped checkpoint. Never stage unrelated changes.

## Failure discipline

Repair and rerun a failed gate before proceeding. A later novelty collision reopens Stage 3. Record
user-authorized deviations in the relevant artifact. Never reinterpret a failed check as a pass.
