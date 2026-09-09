# Privacy policy

Last updated: August 22, 2026.

MerLean is an open-source, locally executed collection of skills for Codex and
Claude Code. The MerLean authors do not operate a MerLean cloud service and do
not receive users' source files, prompts, proof plans, API keys, or generated
artifacts.

## Local data

MerLean reads and writes only the files selected by the user or required by the
active workflow. Lean build products, Python environments, plan databases, and
per-run artifacts remain on the user's machine. Files such as `.env`, `.venv`,
and `.lake` are excluded from the distributed repository.

MerLean does not impose a retention period or maintain a remote copy of this
local data. Users control retention and may delete generated plan-data folders,
paper-writing run folders, Lean build products, and Python environments from
their own machine when they are no longer needed. Removing the plugin does not
automatically delete user-created project files.

An OpenAI API key may be supplied through the `OPENAI_API_KEY` environment
variable or a local, ignored `.env` file. MerLean does not include a default key,
send the key to the MerLean authors, or intentionally log it.

## Optional online plan graph

In the default online plan-graph mode, MerLean sends statement-plan text,
research notes, semantic-search queries, and generated summaries to the OpenAI
API for embeddings, reranking, or language-model processing. Those requests are
made directly from the user's machine with the user's API credentials and are
governed by OpenAI's applicable terms and privacy policy. The embedded Qdrant
database and materialized plan files remain local.

Users who do not want plan content sent through those API calls can set
`PLAN_OFFLINE=1`. Offline mode performs deterministic local storage, search, and
summarization and makes no embedding, vector-store, reranking, or summary API
calls.

## Third-party services

Codex, ChatGPT, GitHub, Python package repositories, Lean, Mathlib, and other
tools invoked by a user are governed by their own terms and privacy policies.
MerLean does not control their processing. Users should not place credentials or
private data in prompts, repositories, proof plans, issue reports, or files they
intend to publish.

## Contact

Privacy questions may be opened through the repository's public issue tracker:
<https://github.com/MerLeanProver/MerLean/issues>.
