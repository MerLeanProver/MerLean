from __future__ import annotations

import json
from pathlib import Path
from typing import Any


THEOREM_KINDS = {"thm", "theorem", "lem", "lemma", "prop", "proposition", "cor", "corollary"}
DEFENSE_KINDS = {"gate", "model", "counterweight", "defense", "test", "audit"}


def load_graph(path: Path) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str]], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str]] = []
    selected: list[str] = []
    if isinstance(data, dict) and isinstance(data.get("statements"), list):
        for raw in data["statements"]:
            node = dict(raw)
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            node.setdefault("node_id", node_id)
            node.setdefault("display_name", node.get("name", node_id))
            node.setdefault("kind", str(node.get("type", "")).lower())
            nodes[node_id] = node
        for node_id, node in nodes.items():
            for dependency in node.get("dependencies", []) or []:
                edges.append((str(dependency), node_id))
        selected = [node_id for node_id in nodes if not any(a == node_id for a, _ in edges)]
    elif isinstance(data, dict) and isinstance(data.get("nodes"), list):
        for raw in data["nodes"]:
            node = dict(raw)
            node_id = str(node.get("node_id") or node.get("id") or "")
            if node_id:
                nodes[node_id] = node
        edges = [(str(e["source"]), str(e["target"])) for e in data.get("edges", [])]
        selected = [str(value) for value in data.get("selected_main_results", [])]
    else:
        raise ValueError("unsupported graph JSON: expected statements[] or nodes[]/edges[]")
    missing = sorted({item for edge in edges for item in edge if item not in nodes})
    if missing:
        raise ValueError("graph edges reference missing nodes: " + ", ".join(missing[:10]))
    return nodes, edges, selected


def topological_order(nodes: dict[str, Any], edges: list[tuple[str, str]]) -> list[str]:
    outgoing = {node_id: [] for node_id in nodes}
    indegree = {node_id: 0 for node_id in nodes}
    for source, target in edges:
        outgoing[source].append(target)
        indegree[target] += 1
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for target in sorted(outgoing[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if len(ordered) != len(nodes):
        raise ValueError("dependency graph contains a cycle")
    return ordered


def analyze(path: Path, selected_override: list[str] | None = None, max_paths: int = 200) -> dict[str, Any]:
    nodes, edges, selected_default = load_graph(path)
    order = topological_order(nodes, edges)
    selected = selected_override or selected_default
    unknown = [item for item in selected if item not in nodes]
    if unknown:
        raise ValueError("unknown selected result(s): " + ", ".join(unknown))
    if not selected:
        raise ValueError("no selected main results; pass --select")

    incoming = {node_id: [] for node_id in nodes}
    for source, target in edges:
        incoming[target].append(source)
    def longest_paths(
        ordered: list[str], parents_by_node: dict[str, list[str]],
    ) -> tuple[dict[str, int], dict[str, list[list[str]]], bool]:
        depth: dict[str, int] = {}
        paths: dict[str, list[list[str]]] = {}
        truncated = False
        for node_id in ordered:
            parents = parents_by_node[node_id]
            if not parents:
                depth[node_id] = 0
                paths[node_id] = [[node_id]]
                continue
            best = max(depth[parent] for parent in parents)
            depth[node_id] = best + 1
            combined: list[list[str]] = []
            for parent in sorted(parent for parent in parents if depth[parent] == best):
                combined.extend(path_value + [node_id] for path_value in paths[parent])
                if len(combined) >= max_paths:
                    truncated = True
                    combined = combined[:max_paths]
                    break
            paths[node_id] = combined
        return depth, paths, truncated

    depth, paths, truncated = longest_paths(order, incoming)

    theorem_ids = {
        node_id for node_id, node in nodes.items()
        if str(node.get("kind") or node.get("type") or "").lower() in THEOREM_KINDS
        or any(str(node.get("kind") or node.get("type") or "").lower().startswith(prefix)
               for prefix in ("thm", "lem", "cor"))
    }
    theorem_edges: set[tuple[str, str]] = set()
    for target in theorem_ids:
        frontier = list(incoming[target])
        visited: set[str] = set()
        while frontier:
            parent = frontier.pop()
            if parent in visited:
                continue
            visited.add(parent)
            if parent in theorem_ids:
                theorem_edges.add((parent, target))
            else:
                frontier.extend(incoming[parent])
    theorem_nodes_map = {node_id: nodes[node_id] for node_id in theorem_ids}
    theorem_order = topological_order(theorem_nodes_map, sorted(theorem_edges))
    theorem_incoming = {node_id: [] for node_id in theorem_ids}
    for source, target in theorem_edges:
        theorem_incoming[target].append(source)
    theorem_depth, theorem_paths, theorem_truncated = longest_paths(theorem_order, theorem_incoming)

    theorem_nodes = []
    defense_nodes = []
    for node_id in order:
        node = nodes[node_id]
        kind = str(node.get("kind") or node.get("type") or "").lower()
        entry = {
            "id": node_id,
            "name": node.get("display_name") or node.get("name") or node_id,
            "kind": kind,
            "statement": node.get("content") or node.get("signature") or node.get("docstring") or "",
            "grade": node.get("grade") or node.get("status") or "UNVERIFIED",
        }
        if kind in DEFENSE_KINDS:
            defense_nodes.append(entry)
        elif kind in THEOREM_KINDS or any(kind.startswith(prefix) for prefix in ("thm", "lem", "cor")):
            theorem_nodes.append(entry)

    terminals = []
    for node_id in selected:
        node = nodes[node_id]
        terminals.append({
            "id": node_id,
            "name": node.get("display_name") or node.get("name") or node_id,
            "depth": depth[node_id],
            "paths": paths[node_id],
            "theorem_depth": theorem_depth.get(node_id),
            "theorem_paths": theorem_paths.get(node_id, []),
            "statement": node.get("content") or node.get("signature") or "",
            "hypothesis_surface": node.get("hypothesis_surface") or "VERIFY AGAINST CERTIFICATE/AUDIT",
            "grade": node.get("grade") or node.get("status") or "UNVERIFIED",
        })
    return {
        "schema_version": 1,
        "graph": str(path.absolute()),
        "selected_main_results": selected,
        "terminals": terminals,
        "theorem_nodes": theorem_nodes,
        "theorem_edges": [
            {"source": source, "target": target} for source, target in sorted(theorem_edges)
        ],
        "defense_artifacts": defense_nodes,
        "paths_truncated": truncated or theorem_truncated,
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = ["# Critical path", "", f"Graph: `{report['graph']}`", ""]
    for terminal in report["terminals"]:
        lines.extend([
            f"## {terminal['name']}", "",
            f"- Node: `{terminal['id']}`",
            f"- Grade: `{terminal['grade']}`",
            f"- Hypothesis surface: {terminal['hypothesis_surface']}",
            f"- Statement: {terminal['statement'] or '[inspect source]' }", "",
            "Theorem-grade deepest path(s):", "",
        ])
        for path in terminal["theorem_paths"]:
            lines.append("- " + " → ".join(f"`{item}`" for item in path))
        lines.extend(["", "Full dependency deepest path(s), including definitions:", ""])
        for path in terminal["paths"]:
            lines.append("- " + " → ".join(f"`{item}`" for item in path))
        lines.append("")
    lines.extend(["## Theorem-grade DAG nodes", ""])
    for node in report["theorem_nodes"]:
        lines.append(f"- `{node['id']}` — {node['name']} — grade `{node['grade']}`")
    lines.extend(["", "## Theorem-grade DAG edges", ""])
    if report["theorem_edges"]:
        for edge in report["theorem_edges"]:
            lines.append(f"- `{edge['source']}` → `{edge['target']}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Defense artifacts", ""])
    if report["defense_artifacts"]:
        for node in report["defense_artifacts"]:
            lines.append(f"- `{node['id']}` — {node['name']}")
    else:
        lines.append("- None classified by the graph; inspect campaign certificates separately.")
    lines.extend(["", "> Gate note: verify every terminal grade and hypothesis surface against actual certificate/audit output.", ""])
    return "\n".join(lines)
