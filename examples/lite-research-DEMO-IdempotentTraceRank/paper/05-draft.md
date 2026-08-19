# STEP 5 — draft record

Draft: `paper.tex` (3 pages, no separate appendix at this scale, no `refs.bib`).

- (i) **Definitions once, just-in-time**: all four census definitions (trace, column
  space/rank, idempotent, ι) live in §Setup, immediately before their first consumers;
  definition census run: 0 `\begin{definition}` environments (definitions are inline in
  §Setup by design at this scale), no duplicates, no notation introduced more than one
  section before use.
- (ii) **Cite-don't-reprove — recorded deviation**: this paper carries **zero
  citations**. The campaign's own audit contradicted the one candidate textbook pointer
  (H&J §number), the ledger closed with zero CITED rows, and every proof here is 2–5
  lines — shorter than a verified citation would be. The locked-bib reference standard
  was therefore not exercised (nothing to verify); the repository is cited once on the
  title page as the protocol's verification-section rule requires.
- (iii) **Appendix**: none — no proof exceeds five lines; nothing qualifies as
  "technical/lengthy".
- (iv) **Factoring**: R2 (characteristic-free proposition) factored OUT of R1's proof
  path so the theorem consumes the proposition — one proof mechanism, stated once.
- (v) **Reference standard**: not exercised (see ii).

GATE 5: (a) definition census ✓; (b) every `\cite` resolves — vacuously, zero cites ✓;
(c) latexmk clean, 3 pages ✓; (d) summary-layer audit — deferred to the combined
post-Step-6 audit (single Opus auditor over abstract + intro + section leads against
the precise statements), recorded in `06-audit.md`.
