"""plan_store — a Mem0-g–backed store for the formalization statement plan.

Replaces statements.json/progress.json with a Mem0 2.x graph where each
statement is one memory node (infer=False) and dependency edges live in node
metadata, kept equal to the real Lean dependency graph (see lean_sync).

Pure helpers under _vendor/ are verbatim copies of utilities from this
project's own predecessor plan store, so nothing here imports from or modifies
external code.
"""

try:  # lazy: store imports mem0; keep _vendor/config usable on their own
    from .store import PlanGraph  # noqa: F401
except Exception:  # pragma: no cover
    PlanGraph = None
