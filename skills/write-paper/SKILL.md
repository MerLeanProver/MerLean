---
name: write-paper
description: "Paper-writing agent — drive a campaign's formalized results into a publishable math paper via the 8-step gated protocol (critical path → framework → main-result selection with fresh novelty check → lemma selection → draft under the definitions-once / cite-don't-reprove / appendix / factoring / locked-bib rules → shrink → abstract+outlook → terminology standardization). Run in the MAIN context; Opus subordinates. Use when asked to write/draft the paper from a campaign."
---

# write-paper

Read and execute, step by step with its gates:

    ${CLAUDE_PLUGIN_ROOT}/paper-writing-agent/claude/AGENT.md

(the file ships with this plugin). That file is the canonical protocol. Arguments:
the campaign directory (any directory in the user's project holding a ledger / plan graph /
certificates; worked examples ship under `${CLAUDE_PLUGIN_ROOT}/examples/` for reference —
never write into the plugin directory). Artifacts land in `<campaign>/paper/`. Every step commits
(local only — never push). The standing rules named in AGENT.md are binding.
