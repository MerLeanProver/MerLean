---
name: lite-research
description: MerLean-lite — resolve an informal math question FAST by working the way a human mathematician does — natural-language proofs first, cheap Python experiments as the screen, adversarial debate as the referee, and Lean 4 fired ONLY at the weakest links. The deliberate INVERSE of auto-research's verification budget — there, every step is kernel-checked and axiom-clean; here, Lean is a scarce resource spent where residual uncertainty is highest, and a targeted certificate proves one contested step from its accepted prior steps as hypotheses. Races parallel high-level routes (each must name the REPRESENTATION that reduces complexity, not a same-strength reformulation), develops the best into a graded step ledger, attacks it with skeptic subagents (hardest on the novel, high-value steps), numerically probes every testable claim, then Lean-certifies only the steps debate could not settle. Output: an NL proof with a per-step evidence ledger, graded BRONZE/SILVER/GOLD. Use when asked to "lite-research / quickly settle / screen" a question, or when full formalization would be too slow for the exploration phase.
---

# lite-research — MerLean-lite: NL-first, Lean at the weakest links

Input: an informal question. Output: a **graded resolution** — a natural-language proof (or
refutation) whose every step carries evidence: debate verdict, numerical support, and — for
the steps that stayed uncertain — a targeted Lean certificate. Speed is a design goal:
most of the run is thinking, debating, and running small Python experiments, not compiling.

**Why this mode exists.** Full formalization at every step is the strongest possible filter
and the slowest. The recent NL-first results (Crouzeix via an adapted CDC-style harness;
Sendov) worked the other way: natural language proof discovery under heavy adversarial
audit, formal verification after. And the post-mortems of failed replications agree on the
bottleneck: audit-heavy pipelines guarantee you are never wrong, but the decisive event is a
REPRESENTATION that reduces the problem's complexity — "after the change of representation,
the original obstruction disappears". lite-research therefore (a) spends its cycles on
route diversity and representation hunting, (b) uses adversarial debate + numerics as the
cheap filter, and (c) reserves Lean for the steps where those filters cannot reach a
verdict. It is the exploration gear; `/auto-research` remains the certification gear.

**The five pillars:**
1. **NL FIRST, LEAN LAST** — no Lean anchor, no formalization phase. The primary artifact
   is the step ledger (§L). Lean fires only through the §L3 triage gate.
2. **REPRESENTATION OVER AUDIT** — every route must name its representation and why it
   reduces complexity; a route whose "idea" is a same-strength rephrasing is rejected at
   birth. When stuck, hunt representations, don't add auditors.
3. **ADVERSARY AS REFEREE** — every step ledger faces skeptic attack; novel/high-value
   steps get the heaviest fire (multiple lenses). A step is *accepted* only when attack
   rounds stop producing live objections.
4. **EXPERIMENT EVERYTHING TESTABLE** — every step with computational content gets a small
   Python probe (random instances, boundary cases, counterexample search) via `explore`.
   Numerics never prove; they kill, support, and localize doubt.
5. **VERDICTS ARE EVIDENCE-BASED** — direction pivots only on independently verified
   witnesses (same gate as auto-research §B6); acceptance/refutation of a step always
   records *why*. Fully autonomous: never ask the user; decide, document, bank.

## Inputs
- `QUESTION` — the informal question/conjecture, verbatim (required).
- `QUESTION_NAME` — optional CamelCase name; propose one if omitted.
- `LIB_DIR` — optional Lean workspace (lakefile dir with Mathlib). Needed ONLY if §L3
  fires; without one, triaged steps are marked `needs-lean (no workspace)` and the run
  still completes at BRONZE.
- `SOURCE` — optional supporting material.
- `ROUTES` (default 3, min 2) — parallel high-level routes in L1.
- `DEBATE_ROUNDS` (default 3) — max repair↔attack rounds per route in L2.

**Derived:** `DATA_DIR` = `<QuestionName>_lite/` (next to `LIB_DIR` if given, else cwd) —
holds `ledger.md` (§L), route pitches, experiment scripts/outputs, Lean certificates.
**Memory:** if the plan graph runtime is initialized (`.venv` + key), bank Notes as in
auto-research §M; otherwise `DATA_DIR/ledger.md` and `DATA_DIR/notes.md` ARE the memory —
same banking discipline, flat files. lite-research must run with zero setup.
**Bare-run adaptations (no `.venv` / plan store / lean-lsp):** tell every subagent in its
dispatch prompt: use `python3` directly; skip all `cli.py` steps (`graph_sync: n/a`); use
the build-command fallback for Lean diagnostics. Certificates compile against `LIB_DIR`
with the copy-in pattern: `cd LIB_DIR && cp <cert> ./Tmp_<name>.lean && lake env lean
Tmp_<name>.lean; rm Tmp_<name>.lean` (lake resolves imports relative to the workspace; a
clean run prints nothing; never `lake update`, never build the whole workspace).
**Resume, don't restart:** existing `DATA_DIR` ⇒ read `ledger.md` + `notes.md`, rejoin.

## Progress reporting
```
▶ <phase>            · <step> …          ✓ <good outcome>       ✗ <problem> → <action>
⇄ <route opened/killed/selected (+why)>  ⚔ <attack round: objections raised/survived>
🔬 <experiment: what → verdict>           ⚖ <step verdict change>   ⛏ <Lean certificate event>
```

## §Roles — five subagents, each at its moment
- **`route-scout`** (background, parallel ×`ROUTES`) — pitches ONE high-level route:
  representation, skeleton, predicted weakest step, kill-test. Diversity is enforced by
  giving each scout a different angle assignment (§L1).
- **`nl-prover`** (background, 1–2 in parallel) — develops one route into a full step
  ledger (§L); later, repairs contested steps.
- **`skeptic`** (background, 1 per ledger per round; parallel lenses on crux steps) —
  attacks a ledger: gaps, circularity, quantifier slips, wrong constants, hidden
  assumptions, false lemmas. Returns per-step objections with severity.
- **`explore`** (reuse, unchanged) — numerical probes (L0 direction, L2 step tests,
  witness verification). Its reliability rules (independent witness re-check, sampling ≠
  enumeration) are load-bearing here — numerics substitute for formal checking.
- **`compile-fix`** (reuse, targeted mode) — proves ONE step-certificate file (§L3);
  `AXIOM_POLICY=strict` still (the "axioms" are hypotheses in the statement, not `axiom`).
Fleet: ≤ 4 background subagents; only compile-fix jobs are RAM-gated (auto-research §R
rules); scouts/skeptics/explores are cheap — prefer breadth there.

## §L The step ledger — the primary artifact
`DATA_DIR/ledger.md`, one table per route. One row per step:
```
S<k> | claim (self-contained, quantifiers explicit) | uses: S<i>,S<j> | class | status | evidence
```
- **class**: `ROUTINE` (standard technique, would be an exercise; cite the standard fact) /
  `COMPUTATION` (finite check or calculation — machine-checkable in principle) /
  `NOVEL` (the route's real content — new object, new inequality, the representation move) /
  `CITED` (a published result used as-is — see the citation gate below).
- **The citation gate (`CITED` rows).** A result qualifies as a **temporarily
  trustworthy** root — proof not re-derived, not debated, never a Lean target — through
  either tier: **(T1-journal)** published in a refereed mathematics venue (journal or
  refereed proceedings), or **(T2-released)** publicly released (arXiv or equivalent) with
  at least one author verifiable as a mathematics professor at a university (faculty page
  or equivalent evidence; the skeptic checks this). Anything below both tiers — anonymous
  preprints, blogs, forum posts — stays NOVEL/ROUTINE and must be proved. Every CITED row
  records its tier, and the report's trust base lists T2 roots separately (they carry more
  residual risk than refereed ones). What IS mandatory at BOTH tiers equally — the tier
  changes only who vouches for the proof, never the required exactness of the match at the
  use site — and what the skeptic attacks with `fatal` severity, is
  the **100% match audit**: the row must carry (a) the full bibliographic pointer down to
  the theorem number, (b) the source's statement verbatim (or a faithful restatement with
  an explicit notation map), and (c) a hypothesis-for-hypothesis checklist showing the use
  site satisfies EVERY hypothesis of the cited statement under the source's own
  conventions (degenerate cases, strictness, normalizations included), and consumes no
  more than its conclusion. "Roughly this" or conclusion-shaped resemblance is a fatal
  objection, not a citation. CITED rows are the NL analogue of declared axioms: each one
  is a named trust root, enumerated in the final report, and the grade is annotated
  "modulo cited results" — a later GOLD pass re-earns them formally or from Mathlib.
- **status**: `drafted → contested(n objections) → accepted | refuted | lean-certified |
  needs-lean`. A ledger is **closed** when every step is `accepted` or `lean-certified`.
- **evidence**: attack rounds survived; experiment ids + outcomes; certificate file; or the
  objection that refuted it.
The union rule: the theorem is proved (BRONZE or better) iff every ledger row of the
winning route is closed and the rows compose (the skeptic's final pass checks composition:
no step uses a refuted or missing row, no circular `uses`).

---

## Phase L0 — understand + probe (no Lean, ~minutes)
1. **A1 discipline from auto-research, minus Lean**: objects, hypotheses, exact claim,
   quantifier shape, degenerate cases, what counts as an answer. Write the *problem
   dossier* at the top of `ledger.md`. Determine-style problems: fix the answer shape
   before routing (probe first if the answer itself is unknown).
2. **Direction probe** — one `explore`: smallest nontrivial cases, random instances, OEIS
   if integer-flavored. Verified counterexample ⇒ the target flips to refutation NOW
   (witness + independent re-check = §B6 gate) and L1 routes become "refutation +
   generalize the witness". Supportive ⇒ proceed to prove. Ambiguous ⇒ one L1 route is the
   disproof hunt.
3. Bank the dossier + probe verdict.

## Phase L1 — route portfolio: representation hunting (parallel)
Dispatch `ROUTES` route-scouts **in parallel**, each with the dossier + probe data + a
distinct assigned angle (rotate through: induction/recursion; explicit construction;
algebraic identity / generating function; extremal-or-exchange argument; analytic bound;
bijection/double counting; invariant/monovariant; contradiction via minimal criminal;
known-theorem specialization — pick the set that fits the domain). Each pitch must contain:
- **representation**: what the objects BECOME (the reformulation), and one sentence on why
  the main obstruction shrinks under it. *Same-strength rephrasing ⇒ reject the pitch.*
- **skeleton**: 3–7 numbered step claims (proto-ledger rows) with classes.
- **weakest step**: the scout's own bet on where it breaks.
- **kill-test**: a ≤5-minute experiment that would falsify the route's key claim.
**Select** 1 favorite + 1 rival (keep the rest banked as dormant pitches): rank by
(representation actually reduces complexity) > (weakest step looks attackable-but-fixable)
> (kill-test survivable). Run each selected route's kill-test via `explore` BEFORE
development; a failed kill-test kills the route at birth (that's it working as intended —
promote a dormant pitch). Portfolio never collapses below 2 until one ledger closes.

## Phase L2 — develop + adversarial debate (per selected route)
1. `nl-prover` expands the skeleton into a full ledger: every row self-contained, every
   `uses` explicit, classes honest (over-claiming `ROUTINE` is the classic hiding spot —
   the skeptic is told to re-classify).
2. **Attack round** (`skeptic`): returns objections `(step, severity ∈ {fatal, gap,
   nitpick}, content, what-would-resolve)`. Crux steps (`NOVEL`, or any step ≥3 other
   steps depend on) get parallel skeptics with distinct lenses: *correctness* (is the
   inference valid), *counterexample* (does a small instance break the claim), *usage*
   (does the step prove what later steps actually consume — the interface lie), *novelty*
   (is this secretly a known-false or known-open claim).
3. **Experiment pass** — for every objection with computational content and every
   `COMPUTATION` row: `explore` probes (structured: exact small cases first, then random;
   report per its reliability rules). An experiment that contradicts a step ⇒ the step is
   `refuted` pending the independent re-check; one that supports ⇒ evidence, never proof.
4. **Repair round** (`nl-prover`, same route): fix `gap`s, rewrite or reroute around
   `fatal`s (a new sub-step, a weakened-but-sufficient claim, or a changed step — the
   ledger versions are kept). Then next attack round.
5. Terminate the loop when: **closed** (an attack round yields zero fatal/gap objections
   ⇒ mark surviving steps `accepted`), **dead** (a `fatal` on the route's representation
   itself, or `DEBATE_ROUNDS` exhausted with fatal objections still live ⇒ kill route,
   promote the rival / a dormant pitch — bank the cause), or **flipped** (a verified
   counterexample to the QUESTION itself ⇒ §B6 pivot: refutation becomes the goal;
   ledgers restart with the refutation dossier).
6. **Stuck ⇒ representation, not audit**: if two consecutive repair rounds leave the same
   fatal objection standing, do NOT add more skeptic rounds — send one route-scout after a
   NEW representation of the stuck step (assigned angle: "make this obstruction
   disappear"), and treat its pitch as a candidate sub-route.

## Phase L3 — weakest-link triage → targeted Lean
When a ledger closes, rank its rows by **residual uncertainty**:
objections survived-but-contested > `NOVEL` with no possible experiment > `COMPUTATION`
checked only by sampling > long chains of quantifier bookkeeping > everything else.
**Fire Lean only on rows where** (i) debate converged by exhaustion rather than agreement
(skeptic conceded "probably fine", not "resolved"), OR (ii) the row is the proof's crux
AND an error there voids the theorem, OR (iii) a `COMPUTATION` row's check was sampled,
not exhaustive. Typical count: 0–3 rows. Everything else is *accepted on debate* — that is
the design, not a compromise.
**The certificate (hypothesis-mode — the inverse of no-axiom mode):** for row S⟨k⟩ with
`uses: S_i…`, write `DATA_DIR/cert/Cert_S<k>.lean`:
`theorem cert_S<k> (h_i : ⟦S_i⟧) … : ⟦S_k⟧ := by sorry` — prior accepted steps enter as
**hypotheses of the statement**, never as `axiom` declarations; only S⟨k⟩'s own inference
is formalized. Dispatch `compile-fix` on it (`LIB_DIR`, `AXIOM_POLICY=strict`,
`STATEMENT_ID=cert_S<k>`; plan-graph search step skipped if no store). Outcomes:
`clean` ⇒ row `lean-certified` (record `#print axioms` output in evidence — must be the
standard three). `needs_update` with decomposition ⇒ the row was a cluster: split the
ledger row accordingly (back to a mini-L2 on the pieces). `failed` after the ladder ⇒ the
row returns to `contested` and L2 resumes — a Lean-resistant "accepted" step is exactly
the signal this mode exists to catch. If formalizing ⟦S_i⟧ faithfully is itself a project
(the encoding problem), bank that as `needs-lean (encoding)` and leave the row accepted on
debate — noted loudly in the report.
`CITED` rows never fire for their own content (the proof is external); when a cert's
`uses` include one, the cited statement enters as a hypothesis like any other ⟦S_i⟧ — so
the use-site inference around it is still certifiable.

## Phase L4 — assemble, grade, report
- **Composition pass**: one final skeptic run on the closed ledger as a whole (row
  interfaces, no circularity, the theorem statement is what L0 promised — nothing
  narrowed).
- **Grades**: **BRONZE** — ledger closed on debate+numerics alone (or `needs-lean` rows
  outstanding for lack of workspace/encoding). **SILVER** — BRONZE + every §L3-triaged row
  `lean-certified`. **GOLD** — handed off to `/auto-research` (seed it with the ledger as
  the route sketch; the winning representation becomes its route 1) and returned
  axiom-clean end-to-end. lite-research's own ceiling is SILVER; say so plainly.
- **Refuted** questions: the witness, the two independent verifications, and (when cheap)
  a `Cert_Witness.lean` `decide`/`norm_num` certificate — a settled "no" at SILVER.
- **Report**: the theorem/refutation in NL; the winning representation and why it reduced
  complexity; the final ledger (every row: class, status, evidence); routes killed and by
  what; experiments run (scripts remain in `DATA_DIR`); certificates and their axiom
  audits; **the trust base** — every `CITED` row with its reference and match audit
  (grades carry the annotation "modulo cited results" whenever this list is nonempty);
  the grade; what GOLD would take.

## Pivot gate (unchanged from auto-research §B6)
Direction flips only on an **independently verified** witness — two separate code paths,
sampling artifacts assumed until re-checked. Bank refuted suspicions so they cannot recur.
The QUESTION never changes; only the direction, loudly.

## No walls, no questions
Missing lemma ⇒ new ledger rows. Stuck route ⇒ representation hunt (§L2.6) or route death,
never a silent stall. Never ask the user; the run ends at a graded report or interruption.
Keep the main context lean: subagent summaries only; the ledger holds the detail.
