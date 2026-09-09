# Trust and intended-model gates

Lean's kernel checks the declaration that it is given. It does not decide whether the
declaration is the theorem that the research question asked for. In particular,
`#print axioms` does not list ordinary theorem parameters or proposition-valued fields of
structures. A theorem can therefore be axiom-clean while merely proving an implication
from the missing mathematics.

MerLean uses the following gates in every research runtime.

## HYPOTHESIS FIREWALL

Every premise is classified transitively as one of:

- `ORIGINAL`: stated by the problem;
- `CONDITION`: introduced for the exact achieved conditional theorem, with status `declared`;
- `DERIVED`: proved from earlier rows/nodes;
- `CITED`: an exact external theorem with its use-site hypotheses discharged;
- `ASSUMED`: a residual premise not supplied by the problem and not yet proved;
- `REFUTED`: false or incompatible with the intended model.

`ASSUMED` premises must never remain proof-local or hidden. Either prove them, source-close
them at the strict boundary below, or freeze a new **conditional theorem face** in which each
one is a direct public antecedent. Every downstream result is then rendered “if these
conditions hold, then …”. A declared condition is not evidence that the condition holds for
the original intended object; it changes the scope of the exact theorem being graded.

`open-residual` and `declared condition` are disjoint states. An unexplained residual prevents
Gold. A declared condition may occur in conditional Gold only when it is frozen before proof,
enumerated in the kernel premise census, exposed as a direct binder rather than a hidden record
field, and propagated through every dependent public theorem.
An introduced condition must never be relabeled `ORIGINAL` or `closed`; its contract entry uses
`condition_premise_ids`, records why the scope was introduced, and remains visibly `declared` even
when the exact implication earns Gold.

Explicit typeclass binders such as `[AddCommGroup G]` are public structural context, not
logical premise rows.  They are nevertheless part of the trust census: schema-v2 contracts
must enumerate every such binder, in signature order, under `structural_binders`, and the
independent audit must explain the structural context.  Their proposition-valued law fields
are thereby universally quantified on the theorem face; custom structures or structures
that store a target-shaped fact still go through the interface and definition-independence
gates.

The contract also enumerates every remaining named non-instance parameter under
`data_binder_ids`. Heavy mode asks Lean itself to classify every binder type as `Prop` or
data, and requires the resulting ordered binder census to agree with the public-premise,
data, and structural lists. Proposition-valued instance binders are rejected; an unknown
custom structural class is not ambient context and must be expanded as a premise or audited
interface. Heavy mode also resolves the head structure of each binder type. Project-defined
structures are rejected unless an intended-model interface names the exact `lean_type` and
supplies its completed adapter; this prevents a target-shaped proposition from being smuggled
through a custom data record.

Mathlib's bundled `TopCat` spaces and `TopCat.Hom` continuous maps are trusted data
structures for this limited census purpose, like `LinearMap` and `AddMonoidHom`: they
package standard-library data and laws, not an intended model. A campaign-defined space,
fibration, or comparison package remains untrusted and requires an intended-model adapter.

The executable census stops after the binder prefix explicitly frozen before the result
colon. In particular, it must preserve a conclusion `¬ P` as the result proposition rather
than unfolding `Not` and misclassifying `P` as an anonymous public premise. This exception
is polarity-specific: a leading positive implication or `∀` after the result colon is a
hidden premise and fails Gold until moved into the named binder prefix. Heavy applies the
same runtime binder and result-shape census to every theorem-face root, not only the root
whose signature equals the frozen target.

## THEOREM-FACE CLOSURE

Every consumed mathematical premise must appear on the public theorem face, be an
`ORIGINAL` hypothesis, or be reached through a proved/cited dependency. Proof-only local
assumptions, proposition-valued structure fields, and definitions that encode the desired
conclusion are included in the transitive premise census. Definitions and constructors
must not make the target true by construction.

## CLASS-VS-CARRIER GATE

A claim that one distinguished class is zero is not interchangeable with a claim that its
whole carrier is subsingleton, that every class is zero, that the domain is empty, or that
the intended object is a zero/toy model. Any stronger replacement requires both a proved
implication or equivalence and proof that the stronger premise holds for the intended
object.

## INTENDED-MODEL GATE

A generic witness, one-point model, or zero construction establishes at most consistency
of an interface. Closure at the intended-model level requires an explicit adapter or
instance for the exact objects in the original question, with every residual field
discharged. For obstruction theory, record the stage, fibre connectivity, coefficient
system, primary/non-primary status, indeterminacy, and why the cited theorem applies at
that stage.

## STRICT /ref BOUNDARY

A classical result may remain at the proof boundary only as a direct theorem antecedent—never
as an unaudited Lean `axiom`. Its manifest entry must bind a hashed primary text under the
manifest-local `ref/` or `refs/`, an exact quote and locator, a notation map, and total
hypothesis/conclusion checklists marked exact. Two independent subagents must re-read the same
hashed source: one attacks source correspondence and one attacks use-site applicability. A
secondary quotation, approximate paraphrase, missing convention, or source absent from `ref/`
is `open-residual`, not a boundary result.

Even an exact source match reaches this boundary only as a last-resort cost decision. Heavy mode
must first record that the result is standard or well known, is not available in Mathlib after a
documented search, and resisted concrete proof/decomposition attempts. It may be deferred only
when formalizing the external theory would be disproportionate to the result's role in the
campaign. Novel, disputed, manuscript-specific, or merely inconvenient facts are never cited
boundaries. Cost never compensates for an inexact source or an undischarged source hypothesis.
Schema-v2 boundary entries therefore require a structured `formalization_cost` record.

When a family of cited operations and laws is naturally represented internally by a custom
structure, the question-level theorem must not take that structure witness as an ordinary data
binder and call the result conditional Gold. Expose the existence claim itself as a
proposition-valued antecedent, for example `hSource : Nonempty SourcePackage` or an equivalent
explicit `Exists`/conjunction, and select the witness only inside the proof. The boundary audit
checks this joint existence statement, flattens every component source id and hypothesis, and
checks compatibility of shared normalization, cup-product, and naturality data. It also requires
a manifest-local `source_closure` index that hash-binds every leaf packet and exact primary
excerpt, its locator and leaf checklist, and every compatibility edge. Its face registry must
equal exactly the manifest assumptions that reference the closure. Two independent joint-face
audits must each bind the complete component-boundary census and the complete edge set
(edge id, exact leaf endpoints, and shared datum); their reports may not be replayed across faces,
and their auditors must differ from the manifest author, Gold auditor, and source auditors.
Cross-campaign paths and composite summaries alone do not close the evidence graph. A cited source
package is not an intended-model interface and must not be registered as one merely to pass the
custom-structure census.

## Grade vocabulary

The only grades are `BRONZE`, `SILVER`, and `GOLD`.

- `BRONZE`: the natural-language ledger closes, subject to its disclosed trust base.
- `SILVER`: every triaged inference is Lean-checked. Parameterized certificates are
  reported as `SILVER (interface-certified)`.
- `GOLD`: the exact frozen public theorem—absolute or conditional—is proved or disproved
  end-to-end and passes the kernel, premise, source-boundary, faithfulness, and intended-model
  gates. Conditional Gold says only that the implication is Gold; it does not discharge its
  antecedents or settle the original unconditional question.

`CITED`, `CONDITIONAL`, and `OVER_INTERFACE` describe scope, never alternate grade tokens.
Any open residual, hidden condition, unmatched source boundary, or uninstantiated interface
not itself frozen as the exact conditional target prevents `GOLD`. Clean axioms are necessary,
not sufficient. Reports must separately record whether the original question is `settled`, a
`conditional_advance`, an `interface_lemma`, or `no_progress`, plus research value; a Gold
tautology is still no progress.

## Executable Gold evidence

`verification-manifest.json` schema version 2 binds a Gold claim to hashed evidence inside
the campaign directory: the frozen target contract and its source files, machine-produced
kernel/root evidence, every derived-premise Lean file, every intended-model adapter, the
definition-independence record, and an independent audit report. Premise, interface, and
theorem-face ids must agree exactly across the contract, kernel evidence, and manifest.
Missing arrays, arbitrary matching labels, plain booleans, and unresolvable declaration
names fail closed.

The heavy auditor generates its own Lean audit module; a manifest-supplied audit body is never
trusted. It rebuilds and imports the exact root module, checks the root at the frozen type using
a typed `example`, prints its axioms, and emits a Lean-environment binder census.
Metadata-only calls cannot award schema-v2 Gold. Source text, audit reports, and definition
independence use structured evidence; a declaration name in a comment, unrelated source file,
or content-free report fails.

Schema-v1 Gold is legacy/unaudited and is rejected by the active grader. Structured semantic
reports must bind the auditor id, target hash, question-status and research-value classifications,
and a nonempty finding for every required check. Boundary reports additionally bind the boundary
id, exact source hash, and public Lean binder. The runtime transcript's axiom set must equal—not
merely be a subset of—the axiom set recorded for the roots.

Plan-graph `add`, `update`, and JSON import may record BRONZE/SILVER metadata but cannot set
`verification_grade=GOLD` or `gold_audit`. Gold evidence is audit-controlled. Reconciliation
clears an existing Gold if its audited Lean source, manifest, or any transitively referenced
evidence digest is stale, or if the proof is no longer clean; compilation status never
manufactures a semantic grade. The target contract must bind the exact target plan node in
`plan_statement_id`. After a read-only Heavy `PASS`, persist the grade only with explicit offline
authority: `PLAN_OFFLINE=1 .../audit-research-grade <MANIFEST> --record-gold --plan-data
<PLAN_DATA_DIR> --statement-id <ID>`. The version-2 receipt freezes the complete manifest-local
evidence snapshot and resolved plan path so later reconciliation fails closed after
child-evidence tampering or receipt replay onto a different node or plan.

The public mode names are MerLean `-lite` (default, target SILVER) and `-heavy` (formerly
Lite off, target GOLD). Heavy may start directly on an existing proof/paper or Lean stub;
it creates the same target node and contracts without fabricating a prior Lite run.
Pure statement translation is an explicitly scoped Heavy procedure, not a graded proof.
The same engine and gates ship in both providers; a paper-writing run never awards Gold.
