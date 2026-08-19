# Read-only paper audit checklist

1. Hash baseline, candidate, state, ledgers, registry, bibliography, and included TeX. Snapshot Git.
2. Run deterministic audit and isolated compile. Treat any project mutation as failure.
3. Compare each locked main result's domain, quantifiers, hypotheses, scope riders, constants,
   inequality directions, and conclusions. Check its main-text prominence and all summaries.
4. Sample every automatic coverage class and inspect every moved/merged/cited/ledger-only item.
   Confirm surviving consumers and complete Markdown recovery records.
5. For body/appendix items, retain the statement in the body and verify both references resolve.
6. Recompute the full selected-result ancestor closure and compare frozen formal dependencies and
   reverse consumers with the current graph and Lean sources. Audit every proof-plan action,
   specialization witness, recovery anchor, and consumer rewire; reject a presentation edge changed
   in only one Markdown artifact or an unrecorded formal-edge change.
7. Census explicit and prose definitions, standing constraints, macro/declaration commands, and
   notation across the expanded root document. Confirm one authoritative occurrence per concept or
   symbol immediately before first technical use, with globally shared setup living once in the
   root main TeX.
8. Check every citation against registry hashes and the downloaded TeX passage. Confirm BibTeX is
   the saved arXiv export and every citation key resolves.
9. Audit title, abstract, introduction, and section leads for claims stronger than precise results.
10. Check field-standard terminology, synonym elimination, and notation collisions.
11. Reject process-numbered paper organization such as `Step 1` or `Stage 2`; a necessary roadmap
    should use unnumbered `itemize` entries beginning with short mathematical summary phrases.
12. Compare the pre-layout and final inventories. Reject body or semantic changes, margins below
    `0.75in`, tiny or condensed type, negative spacing, scaling/cropping tricks, overlap, or layout
    performed before the proof-plan and Lean checks passed.
13. Rehash and resnapshot Git. Return `PASS` only with no residuals; otherwise `FAIL` with exact
    locations and repairs. Never edit.
