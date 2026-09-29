# Paper-writing update: review guide

This is an experimental update to the existing Paper-writing agent, not an additional
public agent or a claim of autonomous mathematical correctness or publication readiness.
The three public agents and six provider packages remain unchanged in number.

## Two related workflows

**Synthesis** extracts supported candidate paper stories from supplied notes. The author
approves an exact contribution before focused assessment. The workflow stops at an
evidence-backed decision and handoff; drafting and new research require separate requests.
See [Research-to-paper synthesis](research-to-paper-synthesis.md).

**Recursive writing** accepts an approved brief and source mathematics, or a synthesis
handoff. An external planner gives a writer one consolidated task. Each manuscript revision
is frozen and checked by independent faithfulness, narrative, notation, and wording roles.
All scheduled reports are collected before repair planning. See
[Recursive paper writer](recursive-writer.md).

The design addresses context and competing-instruction pressure by keeping state outside
individual prompts and separating reviewer responsibilities. These are design motivations,
not measured guarantees of model accuracy or cost savings.

## What reviewers should examine

- State integrity: immutable source/dependency snapshots, revision-bound evidence,
  stale-review rejection, retained findings, and read-only resume/audit behavior.
- Editorial calibration: definition motivation and supporting-result purpose at first
  encounter, locatable justification routes, plain wording, and useful rather than rigid
  notation conventions. Required repairs should not be imposed on harmless alternatives.
- Recovery: interrupted rounds resume without consuming another revision; five reviewed
  revisions are allowed by default, followed by an author-directed pause if needed.
- Compatibility: existing saved schema-version-1 writing runs keep their legacy contract;
  the redesigned protocol requires a new run. Synthesis approvals and evidence boundaries
  remain independent of writing passes.

Faithfulness assumes the approved source mathematics is correct. It checks preservation of
meaning, hypotheses, dependencies, proof reasoning, and evidence status, not routine reproof.
Where required, a second independent faithfulness invocation supplies the additional
equivalence review. Completion also requires isolated compilation and actual rendered-page
inspection. Hashes and role identities do not prove that an invocation was genuinely
independent; the host must execute and attribute the reviews honestly.

## Testing and privacy

Deterministic state-engine regressions are separate from actual editorial evaluations.
Public fixtures use synthetic elementary examples; evaluation expectations belong only to
the coordinator. Private pilot manuscripts, reports, approval records, snapshots, and paths
are not distributed. See [Editorial evaluation](editorial-evaluation.md).

Place real run directories outside this repository, or in a dedicated ignored root such as
`runs/` or `.merlean-local/`. Ignore rules do not protect already tracked files or old commits.
Review the exact proposed Git tree and outgoing history before publication. Preserve tests
and deliberately public examples rather than blanket-ignoring all JSON, PDFs, or outputs.

Run the full unittest suite, research-runtime parity audit, and Codex release audit before
merging. Regenerate the six packages from maintained sources in fresh staging if existing
generated bundles contain local changes. A branch or draft pull request is not a release
tag, installation, or authorization to publish a user's research.
