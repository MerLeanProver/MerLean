# MerLEAN Paper Writing for Codex

A standalone Codex plugin for composing mathematics papers from MerLEAN dependency graphs and
refining existing LaTeX papers without overwriting or silently losing results.

The plugin exposes `$paper-writing` for `compose`, `refine`, `resume`, and `next-version` workflows,
plus the read-only `$paper-audit` skill. Deterministic safeguards are available through
`scripts/paperctl`:

```text
scripts/paperctl next-version paper.tex
scripts/paperctl init-refine paper.tex
scripts/paperctl claim-output --state paper-writing/paper-v1/00-run-state.json
scripts/paperctl critical-path statements.json --select Thm_PaperRoot
scripts/paperctl freeze-shrink --state paper-writing/paper-v1/00-run-state.json
scripts/paperctl audit --state paper-writing/paper-v1/00-run-state.json
scripts/paperctl compile paper-v1.tex
```

An unversioned input is v0 and produces `-v1.tex`; an existing next-version target is never
overwritten. The source paper and recursively included TeX/Bib files are hash-locked. Changed
content must be mapped in the coverage ledger, and locked main results receive stronger semantic and
prominence checks.
