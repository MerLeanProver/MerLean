"""Human-readable text rendering of the plan — a status dashboard and an
analytics summary, so a run's progress and current state are easy to read."""

ICON = {
    "completed": "✓", "completed_axiom": "⊛", "in_progress": "◐",
    "pending": "○", "failed": "✗",
}
_ORDER = ["pending", "in_progress", "completed", "completed_axiom", "failed"]


def _bar(done: int, total: int, width: int = 22) -> str:
    if total <= 0:
        return "─" * width
    filled = round(width * done / total)
    return "█" * filled + "░" * (width - filled)


def _fmt_secs(s: float) -> str:
    s = int(s)
    if s >= 3600:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


def render_status(graph, name: str = "") -> str:
    nodes = graph.topo_sorted()
    total = len(nodes)
    by: dict[str, int] = {}
    for n in nodes:
        by[n.get("status", "?")] = by.get(n.get("status", "?"), 0) + 1
    done = by.get("completed", 0) + by.get("completed_axiom", 0)
    pct = (100 * done // total) if total else 0
    cycles = graph.find_cycles()

    L = [f"Plan: {name}" if name else "Plan", "─" * 64]
    L.append(f"  {_bar(done, total)}  {done}/{total} done ({pct}%)"
             f"    cycles: {'none' if not cycles else cycles}")
    counts = " · ".join(f"{ICON[s]} {s.replace('_', ' ')} {by[s]}" for s in _ORDER if by.get(s))
    if counts:
        L.append("  " + counts)
    L.append("─" * 64)
    for n in nodes:
        st = n.get("status", "?")
        deps = len(n.get("dependencies") or [])
        decls = len(n.get("declarations_defined") or [])
        L.append(f"  {ICON.get(st, '?')} {st:<15} {n['statement_id']:<26} "
                 f"{(n.get('type') or ''):<11} deps:{deps}  decls:{decls}")
    return "\n".join(L)


def render_analytics(graph, name: str = "") -> str:
    a = graph.analytics()
    ps = a.get("per_statement", {})
    L = [f"Analytics: {name}" if name else "Analytics", "─" * 64]
    tok = tools = 0
    for sid, rec in ps.items():
        hist = rec.get("status_history") or []
        cur = hist[-1]["status"] if hist else "?"
        L.append(f"  {ICON.get(cur, '?')} {sid}   ({cur})")
        # status timeline (compact)
        if len(hist) > 1:
            L.append("      " + " → ".join(h["status"] for h in hist))
        for sub in rec.get("subagents") or []:
            t = sub.get("tokens", 0); u = sub.get("tool_uses", 0); d = sub.get("duration_ms", 0)
            tok += t; tools += u
            L.append(f"      {sub.get('role', '?'):<19} tokens:{t:>9,}  tools:{u:>3}  "
                     f"time:{_fmt_secs(d / 1000)}")
    L.append("─" * 64)
    L.append(f"  totals   subagent tokens:{tok:>10,}   tool calls:{tools}")
    if a.get("updated_at"):
        L.append(f"  updated  {a['updated_at']}")
    return "\n".join(L)
