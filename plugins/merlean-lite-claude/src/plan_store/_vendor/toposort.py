"""Topological sort + cycle detection.

Verbatim from src/autoformalization/scripts/statement_io.py
(find_dependency_cycles, topologically_sort_statements). Pure functions over
lists of statement dicts ({"id": ..., "dependencies": [...]}).
"""

from typing import Callable, Optional


def find_dependency_cycles(statements: list[dict]) -> list[list[str]]:
    """Return non-trivial strongly-connected components of the dep graph.

    Each returned list is the statement IDs of one cycle, in topological-
    walk order within the SCC (Tarjan's). A returned `[A, B, C]` means
    `A -> B -> C -> A` (or some rotation of that cycle). Empty list means
    the graph is a clean DAG.

    External deps (ids not in the statement list) are ignored, matching
    `topologically_sort_statements`'s behaviour.
    """
    if not statements:
        return []
    id_to_idx: dict[str, int] = {
        s.get("id", ""): i for i, s in enumerate(statements) if s.get("id")
    }
    n = len(statements)
    graph: list[list[int]] = [[] for _ in range(n)]
    for i, s in enumerate(statements):
        for dep in s.get("dependencies", []) or []:
            j = id_to_idx.get(dep)
            if j is not None and j != i:
                graph[i].append(j)

    # Iterative Tarjan — recursion depth would blow on a 100+-stmt project.
    index_counter = [0]
    indices = [-1] * n
    lowlinks = [0] * n
    on_stack = [False] * n
    scc_stack: list[int] = []
    sccs: list[list[int]] = []

    for start in range(n):
        if indices[start] != -1:
            continue
        work: list[tuple[int, int]] = [(start, 0)]
        call_stack: list[int] = []
        while work:
            v, pi = work[-1]
            if pi == 0:
                indices[v] = lowlinks[v] = index_counter[0]
                index_counter[0] += 1
                scc_stack.append(v)
                on_stack[v] = True
            if pi < len(graph[v]):
                work[-1] = (v, pi + 1)
                w = graph[v][pi]
                if indices[w] == -1:
                    call_stack.append(v)
                    work.append((w, 0))
                elif on_stack[w]:
                    lowlinks[v] = min(lowlinks[v], indices[w])
                continue
            if lowlinks[v] == indices[v]:
                component: list[int] = []
                while True:
                    w = scc_stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == v:
                        break
                if len(component) > 1:
                    sccs.append(component)
            work.pop()
            if call_stack:
                parent = call_stack.pop()
                lowlinks[parent] = min(lowlinks[parent], lowlinks[v])

    return [
        [statements[i].get("id", "?") for i in reversed(component)]
        for component in sccs
    ]


def topologically_sort_statements(
    statements: list[dict],
    *,
    log_fn: Optional[Callable[..., None]] = None,
) -> tuple[list[dict], bool]:
    """Reorder statement dicts so every dep appears before its dependents.

    Kahn's algorithm with a min-heap keyed by original position: this keeps the
    result stable — statements already in a valid order keep their exact
    positions. Only entries that violate dependency order move.

    External dependencies (IDs not appearing as a statement in this list) are
    ignored. Cycles are broken by emitting the cyclic nodes in their original
    order at the end, with a structured cycle log per SCC.

    Returns (sorted_list, order_changed).
    """
    import heapq

    if not statements:
        return statements, False

    n = len(statements)
    id_to_idx: dict[str, int] = {}
    for i, s in enumerate(statements):
        sid = s.get("id", "")
        if sid:
            id_to_idx[sid] = i

    in_degree = [0] * n
    dependents: list[list[int]] = [[] for _ in range(n)]
    for i, s in enumerate(statements):
        for dep in s.get("dependencies", []) or []:
            j = id_to_idx.get(dep)
            if j is not None and j != i:
                dependents[j].append(i)
                in_degree[i] += 1

    heap: list[int] = [i for i in range(n) if in_degree[i] == 0]
    heapq.heapify(heap)

    order: list[int] = []
    while heap:
        i = heapq.heappop(heap)
        order.append(i)
        for j in dependents[i]:
            in_degree[j] -= 1
            if in_degree[j] == 0:
                heapq.heappush(heap, j)

    if len(order) < n:
        remaining = [i for i in range(n) if i not in set(order)]
        cyclic_ids = [statements[i].get("id", "?") for i in remaining]
        if log_fn:
            cycles = find_dependency_cycles(statements)
            log_fn(
                "ERROR", "TOPO_SORT_CYCLE",
                f"DEPENDENCY_CYCLE found ({len(cycles)} SCC(s), "
                f"{len(remaining)} cyclic node(s)) — sort fell back to "
                f"disk order for cyclic nodes. Cyclic set: {cyclic_ids}",
            )
            for k, cyc in enumerate(cycles):
                log_fn(
                    "ERROR", "TOPO_SORT_CYCLE",
                    f"SCC#{k} size={len(cyc)} edges: " + " -> ".join(cyc + [cyc[0]]),
                )
        order.extend(remaining)

    sorted_list = [statements[i] for i in order]
    order_changed = any(i != j for i, j in zip(order, range(n)))
    return sorted_list, order_changed
