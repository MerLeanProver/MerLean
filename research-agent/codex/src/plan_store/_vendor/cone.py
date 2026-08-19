"""Forward dependency cone (downstream dependents).

Adapted from src/autoformalization/scripts/compile_loop.py::_forward_dependency_cone.
The original read statements.json from disk; this pure version takes the
statement dicts directly. Algorithm (reverse-edge BFS) is unchanged.
"""


def forward_dependency_cone(statements: list[dict], root_ids: set[str]) -> set[str]:
    """Return the set of statements that transitively depend on any id in root_ids.

    Walks the reverse-edge closure of `dependencies`. The returned set always
    includes `root_ids` themselves.
    """
    if not root_ids:
        return set()

    # Build reverse edges: dep -> {dependents}
    reverse: dict[str, set[str]] = {}
    for s in statements:
        sid = s.get("id", "")
        if not sid:
            continue
        for dep in s.get("dependencies", []) or []:
            reverse.setdefault(dep, set()).add(sid)

    cone: set[str] = set()
    frontier = set(root_ids)
    while frontier:
        nxt: set[str] = set()
        for sid in frontier:
            if sid in cone:
                continue
            cone.add(sid)
            nxt |= reverse.get(sid, set())
        frontier = nxt - cone
    return cone
