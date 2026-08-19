"""LeanSearch-v2-style reranking for plan retrieval.

LeanSearch-v2 runs a two-stage retriever: an embedding model recalls candidates, then a
cross-encoder (Qwen3-Reranker) judges relevance per (query, document) pair. We keep the
OpenAI embedding API for stage 1 (see store.search) and mirror the reranker here with an
OpenAI LLM that scores each candidate's relevance to the query over its informal+formal
representation (`content` + `anchor`).

The two-stage design and the reranker instruction below are adapted from LeanSearch v2
(https://github.com/frenzymath/LeanSearch-v2), Apache License 2.0. Modified here: the
cross-encoder is replaced by an OpenAI LLM scoring 0-10, the instruction is rewritten for
plan-graph nodes rather than Mathlib declarations, and a variant for informal research
notes was added. See the NOTICE file at the repository root.
"""

import json
import os

# Instruction adapted from LeanSearch-v2's reranker instruction (Apache-2.0; see NOTICE).
_INSTRUCTION = (
    "Judge how mathematically relevant each candidate statement is to the Query. "
    "If the query asks for a theorem/lemma, prefer theorem/lemma entries; if it asks for a "
    "definition, prefer definition/instance entries. Score each candidate 0-10 "
    "(10 = exactly what the query is looking for, 0 = unrelated)."
)

# Instruction for the informal group (research notes / the plan summary).
NOTE_INSTRUCTION = (
    "Judge how relevant each candidate research note is to the Query. Prefer entries "
    "whose claim directly answers or bears on the query; among comparable entries prefer "
    "higher-confidence and more recent ones. Score each candidate 0-10 "
    "(10 = exactly what the query is looking for, 0 = unrelated)."
)


def _doc(node: dict) -> str:
    """The informal+formal representation of a statement node (what the reranker reads)."""
    parts = [f"{node.get('type', '')} {node.get('name', '')}".strip()]
    if node.get("content"):
        parts.append(str(node["content"]))
    if node.get("anchor"):
        parts.append("Formal: " + str(node["anchor"]))
    if node.get("confidence"):
        parts.append(f"Confidence: {node['confidence']}")
    if node.get("source"):
        parts.append(f"Source: {node['source']}")
    if node.get("updated") or node.get("created"):
        parts.append(f"Last updated: {node.get('updated') or node.get('created')}")
    return "\n".join(p for p in parts if p)


def rerank(query: str, candidates: list[dict], top_k: int, model: str | None = None,
           instruction: str | None = None) -> list[dict]:
    """Reorder `candidates` (node dicts) by LLM relevance to `query`; return the top_k,
    each annotated with `_rerank_score`. Falls back to the input order on any failure."""
    if not candidates:
        return []
    model = model or os.getenv("PLAN_RERANK_MODEL", "gpt-4o-mini")
    items = [(c["statement_id"], _doc(c)) for c in candidates]
    prompt = (
        f"{instruction or _INSTRUCTION}\n\nQuery: {query}\n\nCandidates:\n"
        + "\n".join(f"[{sid}]\n{doc}\n" for sid, doc in items)
        + '\n\nReturn ONLY JSON of the form {"scores": {"<id>": <0-10>, ...}} '
          "with one entry per candidate id above."
    )
    try:
        from openai import OpenAI
        resp = OpenAI().chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        scores = json.loads(resp.choices[0].message.content).get("scores", {})
    except Exception:
        scores = {}

    by_id = {c["statement_id"]: c for c in candidates}

    def _score(sid: str) -> float:
        try:
            return float(scores.get(sid, -1))
        except (TypeError, ValueError):
            return -1.0

    # Keep the embedding order as the stable tiebreak when scores are missing/equal.
    order = {c["statement_id"]: i for i, c in enumerate(candidates)}
    ranked = sorted(by_id, key=lambda s: (-_score(s), order[s]))
    return [{**by_id[s], "_rerank_score": _score(s)} for s in ranked[:top_k]]
