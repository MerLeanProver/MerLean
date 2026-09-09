# MerLean repository

This repository maintains three agents × two providers: **MerLean Lite**, **MerLean Heavy**,
and **Paper-writing**, each for Claude Code and Codex. Fresh unqualified MerLean research
defaults to Lite (target SILVER). Explicit `-heavy`, former lite-off, or requested full
formalization/proof completion selects Heavy (target GOLD). Paper writing preserves grades.

## Source of truth

- `workflows/merlean-lite.md`, `merlean-heavy.md`, `paper-writing.md`: public entry templates.
- `workflows/common.md`: shared mode, trust, scope, persistence, and capacity policy.
- Other `workflows/*.md` and `roles/*.md`: internal procedures, not extra public agents.
- `ports/claude.md`, `ports/codex.md`: provider adaptations.
- `src/`: one maintained plan/grade/paper engine. Do not create provider runtime copies.
- `scripts/build_bundles.py`: generates six self-contained packages in `plugins/` (included in public release commits).
  Never hand-edit generated packages; rebuild only receipt-verified unchanged outputs.
- `scripts/merlean`: plan CLI; `scripts/merlean-agent`: mode/entrypoint selector, not an LLM launcher.
- `scripts/paperctl`: deterministic paper operations; `scripts/setup.sh`: shared setup.

For actual research, read the selected entry, provider adapter, shared contract, and all
required internal references completely. Ordinary repository maintenance is not a request to
run autonomous mathematics. For explicit translation-only requests, Heavy uses its internal
statement translation workflow and does not prove or award a research grade.

## Preserved research invariants

Kernel cleanliness is necessary, not sufficient. Read `docs/trust-and-instantiation-gates.md`.
Gold requires the exact frozen theorem, closed public-premise/theorem-face census, intended
objects/adapters, definition independence, independent audits, and live Lean verification.
Every condition is a direct public antecedent propagated to consumers. Exact literature
boundaries additionally require hashed primary text and independent source/use-site audits,
plus the established cost-of-formalization decision. Conditional Gold is not an unconditional
answer. Lite cannot award Gold; neither a selected mode nor completed plan status earns a grade.

Main alone writes the plan graph. Workers own disjoint files and return patches/evidence.
Maintain failure-log.md and resume contracts; do not restart campaigns blindly. Checkpoints
are progress while an authorized goal remains open, subject to user interruption and limits.
GPT main/worker defaults are `gpt-6-astra`; preserve explicit choices and Anthropic model IDs.
Retry explicit model-capacity failures every 10 seconds under common.md, without overriding
rate-limit handling or duplicating running jobs. No rule can revive a host that cannot resume.

## Maintenance and release

Run `python3 -m unittest discover -s tests`, `python3 scripts/audit_research_runtime_parity.py`,
and `python3 scripts/audit_codex_release.py` after changes. Existing Gold/source/receipt tests
must remain substantive. Use independent audits for changes to these trust boundaries.
Regenerate all six packages and check their skills/manifests when public entrypoints change.
Never include credentials, Lean/Python caches, campaign state, or unrelated research in bundles.

Publish only with explicit user authorization and independent privacy/release audits.
The public tree must contain only the intended demo example, with no credentials,
private research/session records, or runtime caches. Review the outgoing Git ancestry
as well as the current files. Never publish private preservation branches or use a
mirror/all-branches push. Preserve user work locally before any sanitization.
Do not reinstall user-wide plugins without authorization.
