# PAPER-WRITING AGENT (the 8-step gated protocol, 2026-08-18)

Run in the MAIN context as the orchestrator. Subordinate dispatches (scouts, verifiers,
reference hunters, drafting passes) use `model: "opus"` per the standing model-role split.
Every step produces a named artifact in the paper's working directory and is committed
(local only — never push) before the next step begins. Steps are GATED: a step's exit
checklist must pass before the next step opens.

## Inputs (fixed at invocation)

- `CAMPAIGN_DIR` — the campaign home (the ledger, dossier/novelty/citation records
  where present, cert/). Default:
  `examples/lite-research-DEMO-IdempotentTraceRank/`.
- `PLAN_GRAPH` — the dependency graph. Default: the campaign's Mem0-g plan store
  (`<campaign>_data/`; query via the `plan-graph` skill / `plan_store` CLI). Where the
  campaign's dependency structure instead lives in cert-file embeds + ledger blocks (the
  lite campaigns), derive the graph from: each cert file's embedded-region manifest
  (A embeds B ⟹ A depends on B) + each theorem's `#print axioms` cone + the ledger's
  per-delivery "consumes/discharges" records. Record which source was used.
- `PAPER_DIR` — output: `CAMPAIGN_DIR/paper/` (create; `paper.tex`, `refs.bib`,
  `appendix.tex`, and the per-step artifacts below).

## Standing rules (binding, from the campaign's memory — violations are defects)

- **No Lean in the paper.** No Lean identifiers, no code, no file names in the .tex. The
  verification section describes the trust model in prose and cites the repository once.
  (FORMALIZATION-TARGETS/dossier §5 is the source; the paper compresses it.)
- **arXiv statement style.** Standing setup stated ONCE, then never re-mentioned in
  statements; statements contain the claim only; multi-claim statements itemized;
  claims-vs-proof accounting — every claim in a statement is either proved where stated,
  cited, or removed.
- **Coarse/fine proofs.** Main statements get coarse-grained proofs (the main point,
  one-can-check granularity); workhorse lemmas keep fine-grained proofs (appendix).
- **Math-first style.** Inequalities and named objects over storytelling. No non-academic
  words. No invented nouns where the field has a standard one.
- **Summary-layer discipline.** Every restatement of a result (abstract, intro, section
  leads) must be weaker-or-equal to the precise statement. Shorter ⟹ weaker, never
  stronger. Scope riders and quantifiers travel with every restatement.
- **Grade honesty.** The verification section uses the dossier's three-tier language
  (kernel-checked absolutely / kernel-checked modulo named literature-verified axioms /
  named hypothesis). Never conflate the accounting counts; cite the census with its
  method. The travelling residuals appear wherever a formalized status is claimed.
- **Credit splits verbatim.** Where the ledger records a credit split (a result half-due
  to a cited work, published identities, classical cores), the paper carries it in the
  same sentence as the claim.

---

## STEP 1 — the critical path

Read the dependency graph (see PLAN_GRAPH above). Deliver `paper/01-critical-path.md`:
- The full DAG restricted to theorem-grade nodes (drop gates, models, counterweights —
  list them separately as "defense artifacts" for possible §Verification mention).
- THE CRITICAL PATH(S): the longest/deepest chains ending at the campaign's strongest
  results, with each node's one-line statement and its grade
  (absolute / cited / hypothesis-mode).
- For each terminal node: its full hypothesis surface (the named structures it consumes).

GATE 1: every terminal node's grade and hypothesis surface verified against the actual
cert files' audit output (not the ledger's prose — the files).

## STEP 2 — the empty section framework

Deliver `paper/02-framework.tex`: the section skeleton of a standard mathematics paper,
EMPTY (\section + one-line scope comments only):

  1. Introduction (context, the question, main results informally, related work, outline)
  2. Preliminaries / Setup (definitions and notation — populated later, just-in-time rule)
  3–k. One section per main-result cluster (named after the mathematics, not the campaign)
  k+1. Verification (the trust model, compressed from dossier §5)
  k+2. Outlook / open problems
  Appendix A… (technical lemmas, lengthy proofs)
  References

No content yet. GATE 2: the framework compiles under latexmk with empty sections.

## STEP 3 — main-result selection + novelty double-check + title/theme

3a. From the critical path, select the MAIN RESULTS (2–4): strongest, deepest on the
    path, and forming ONE through-line (the significance-discipline rule: each must
    answer "which gap does it fill; what is now known that wasn't").
3b. NOVELTY DOUBLE-CHECK, per result: reuse NOVELTY-OF-RECORD.md where it already covers
    the result, then run a FRESH arXiv sweep for anything published since the record's
    date (dispatch an Opus verifier; the record's method: verdicts CLEAR/ADJACENT/
    COLLISION with evidence; summarizer output is never evidence — read the TeX).
    A COLLISION demotes the result and reopens 3a.
3c. Decide TITLE + MAIN THEME. Title = a name, not a summary; field-standard nouns.
Deliver `paper/03-main-results.md` (the selected results with their precise statements,
per-result novelty verdicts with evidence pointers, the title, a 3-sentence theme).

GATE 3: every selected result CLEAR or properly-scoped-ADJACENT with the delta sentence
written; the through-line stated in one sentence.

## STEP 4 — the supporting-lemma selection

With the main results fixed, walk their dependency cones and select the IMPORTANT lemmas
(the nodes a reader needs to follow the proofs — not every node; the harness proved far
more than the paper should print). For each: write the paper-facing STATEMENT (arXiv
statement style; the definition-dependencies it needs, listed).
Deliver `paper/04-lemmas.md`: the lemma list in dependency order, each with (statement,
where its proof will live: inline / appendix / citation, and — for citation — the source
candidate).

GATE 4: the union of definition-dependencies across main results + lemmas = the exact
definition list for Step 5.i (no definition without a consumer; no consumer without a
definition).

## STEP 5 — organize and draft

Draft `paper.tex` + `appendix.tex` + `refs.bib` under these binding rules:

  (i) DEFINITIONS ONCE, JUST-IN-TIME. Each concept/notation defined exactly once,
      immediately before first use. After drafting, run a definition census: grep every
      \begin{definition}/notation introduction; any duplicate or any definition appearing
      more than one subsection before its first use is a defect. Remove redundant parts
      of definitions (clauses no consumer uses).
  (ii) NO PROOFS FOR TEXTBOOK/LITERATURE STEPS. If a step is textbook-level or exists in
      a paper, cite it — even where we formalized it in Lean. Every such citation follows
      the REFERENCE STANDARD (below). The Lean formalization of such steps is mentioned
      only in aggregate in §Verification, never per-step.
  (iii) TECHNICAL LEMMAS AND LENGTHY PROOFS → APPENDIX, with the two-way references
      (statement in the main text where needed, proof in the appendix, \ref both ways).
  (iv) FACTORING (optional but attempted): where two definitions/constructions are
      instances of one, factor into a single definition with parameters; where two proofs
      share a mechanism, extract the shared lemma. Goal: reduce total length. Any factor
      that changes a statement's strength is forbidden (summary-layer rule).
  (v) THE REFERENCE STANDARD (for every paper not already treated this way in
      CAMPAIGN_DIR/refs or the registry). For the i-th new reference:
        1. Browse the internet; find the arXiv version — confirm by title, abstract,
           authors.
        2. If confirmed: download the TeX source from https://arxiv.org/e-print/[id],
           decompress into PROJECT/refs/ (create refs/ if none; naming: id with
           underscores).
        3. Read the .tex; verify it contains what we need. If yes: COMMIT to cite it.
           If the content is absent: find and verify a similar paper instead.
        4. If no arXiv version exists: switch to a similar paper that has one (or, for
           books, the campaign's book protocol: public PDF into refs/books/, read,
           verify; user escalation if no public copy).
        5. After commitment: take the BibTeX from the arXiv abs page's
           "Export BibTeX citation" — verbatim, no hand-written entries for arXiv works.
      References already in refs/ with registry/ledger verification records are DONE —
      reuse their entries; do not re-download.

Deliver: the full draft. GATE 5: (a) the definition census passes; (b) every \cite
resolves to a refs/-verified source or a registry record; (c) latexmk compiles clean;
(d) a summary-layer audit pass (an Opus skeptic reads intro+section-leads against the
precise statements; strikes propagate).

## STEP 5½ — SHRINK

A dedicated compression pass over the drafted .tex (runs after the Step-5/6 content exists;
in a live run where Step 6 started first, run it after Step 6 and re-check Gate 6 after):

- **Boring + elementary + unnecessary steps: DELETE from the .tex** — but preserve every
  deleted step verbatim in `paper/deleted-steps.md` (with its original location, the
  reason for deletion, and what the reader is now trusted to supply). Deletion may never
  change what a statement claims (summary-layer rule); if removing a step would force a
  statement to silently strengthen or a proof to gap, the step is not "unnecessary".
- **Boring + important steps: KEEP, but move the proof/derivation to the appendix**, with
  the two-way \label/
ef system: the calling site 
ef's the appendix proof, the appendix
  proof 
ef's back to every calling site. No orphaned appendix material (everything in the
  appendix is 
ef'd from the body at least once).
- The classification of every touched step (deleted / moved / left) is recorded in
  `paper/05.5-shrink.md` with one-line reasons.

GATE 5½: (a) latexmk clean after the pass; (b) the two-way 
ef audit passes (every
appendix item referenced from the body; every body 
ef resolves); (c) a page-count delta
is reported (the pass must shrink, not grow, the main text); (d) a statement-integrity
check — every theorem/lemma/corollary statement byte-identical before and after the pass
(diff the statement environments; proofs may change, statements may not).

## STEP 6 — abstract, title (final), outlook

Write the abstract LAST (from the actual content): ≤ 200 words, the through-line, the
main results at weaker-or-equal strength, the verification model in one honest clause.
Confirm or revise the Step-3 title against the finished content. Write §Outlook from the
campaign's recorded open problems (the dossier's remaining-surface list; each open item
stated as a question, with what is known).
GATE 6: the abstract survives the summary-layer audit against every statement it
compresses.

## STEP 7 — terminology and notation standardization

A dedicated full pass (dispatch an Opus editor + verify):
- Build the TERMINOLOGY TABLE: every concept → the ONE field-standard term used
  (quantum-logic side per Mingsheng Ying's usage where applicable; topology per
  Hatcher's; the campaign's own coinages only where the ledger records no standard term
  exists, introduced explicitly as "which we call…").
- Every synonym occurrence replaced by the chosen term. Every notation used for two
  things, or two notations for one thing, resolved. Known collisions from the ledger
  (e.g. Q as half-perimeter vs the polynomial) checked explicitly.
- Remove made-up words; reduce vocabulary diversity.
Deliver `paper/07-terminology.md` (the table) + the standardized .tex.
GATE 7: a grep-based synonym audit over the final .tex against the table returns zero
unresolved synonyms; the notation index has no collisions.

## STEP 8 — done

Final checks: latexmk clean; all gates' artifacts present; the repair-record appendix of
the dossier updated with "paper vN drafted"; commit. Report to the user: the title, the
main results as printed, the reference count (verified/total), the length, and the open
items list. STOP — the user reviews before any further iteration.

## Failure discipline

Any gate failure: fix and re-run the gate before proceeding — never carry a known defect
forward. Any novelty COLLISION at any step: stop, record, reopen Step 3. Any conflict
between this protocol and the user's live instructions: the user wins; record the
deviation in the step artifact.
