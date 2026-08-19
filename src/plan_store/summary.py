"""Generate an LLM narrative summary of the plan, store it as a searchable meta node
(`Summary`), and write `summary.md` into the data folder.

This is the domain-specific analog of Mem0's procedural-memory summary: instead of
summarising a human↔agent conversation, we summarise the statement plan — what the library
establishes and how its lemmas compose — with one OpenAI call.
"""

import os
from pathlib import Path


def _statements_block(graph) -> str:
    lines = []
    for n in graph.topo_sorted():  # statement nodes only (meta excluded), dependency order
        deps = ", ".join(n.get("dependencies") or []) or "—"
        lines.append(
            f"- [{n.get('status')}] {n.get('type')} {n['statement_id']} ({n.get('name')}): "
            f"{n.get('content', '')}  (deps: {deps})"
        )
    return "\n".join(lines)


def generate_summary(graph, name: str = "", model: str | None = None) -> str:
    model = model or os.getenv("PLAN_SUMMARY_MODEL", "gpt-4o-mini")
    block = _statements_block(graph)
    if not block.strip():
        return f"# {name or 'Plan'} — summary\n\n(No statements in the plan yet.)"
    prompt = (
        f"You are summarising a Lean 4 formalization plan named '{name}'. Its statements, in "
        "dependency order, are listed below (status, type, id, name, content, dependencies).\n\n"
        f"{block}\n\n"
        "Write a concise narrative summary in markdown with three short sections:\n"
        "1. **Overview** — what the library / main theorem establishes (one paragraph).\n"
        "2. **Proof architecture** — how the helper lemmas compose into the main result "
        "(the dependency flow and the key ideas).\n"
        "3. **Status** — what is proved vs. still pending.\n"
        "Be mathematically precise and faithful; do not invent content beyond what is given."
    )
    from openai import OpenAI
    resp = OpenAI().chat.completions.create(
        model=model, temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def summarize(graph, data_dir, name: str = "", model: str | None = None) -> dict:
    """Generate, store (as the `Summary` node), and write `summary.md`. Returns the text + paths."""
    text = generate_summary(graph, name=name, model=model)
    graph.upsert_summary(text)
    out = Path(data_dir) / "summary.md"
    out.write_text(text, encoding="utf-8")
    return {"summary": text, "summary_md": str(out), "node": "Summary", "chars": len(text)}
