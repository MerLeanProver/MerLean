"""Render a plan-graph library as a Graphviz diagram.

Two layers in one picture:
  * statement nodes, colored by status, connected by their dependency edges;
  * each statement that defines several declarations is drawn as a cluster showing
    the *internal* declaration-level dependency DAG (read from the real .lean file
    via the vendored DependencyAnalyzer) — e.g. which helper lemmas feed the main
    theorem.
"""

import shutil
import subprocess
from pathlib import Path

from ._vendor.lean_parser import DependencyAnalyzer
from .lean_sync import lean_file_for

_STATUS_COLOR = {
    "completed": "#c8f0c8", "completed_axiom": "#c8e0ff", "pending": "#eeeeee",
    "in_progress": "#fff1b0", "failed": "#ffc8c8",
}
_DECL_SHAPE = {
    "theorem": "ellipse", "lemma": "ellipse", "proposition": "ellipse",
    "corollary": "ellipse", "def": "box", "abbrev": "box", "structure": "box",
    "instance": "box", "class": "box", "inductive": "box", "axiom": "hexagon",
}


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _decl_deps(node, lib_dir, cache):
    """Declaration-level deps {decl: [decl names]} from the statement's .lean file."""
    if not lib_dir:
        return None
    f = lean_file_for(node, Path(lib_dir))
    if not f.exists():
        return None
    key = str(f.parent)
    da = cache.get(key)
    if da is None:
        da = DependencyAnalyzer(f.parent)
        da.build_registry(f.parent)
        cache[key] = da
    raw = da.find_declaration_dependencies(f)
    # labels look like "thm:Namespace.name" — reduce to the short declaration name.
    return {k: [x.split(":")[-1].split(".")[-1] for x in v] for k, v in raw.items()}


def _rep(node):
    """The node id used as the endpoint for statement-level edges."""
    sid = node["statement_id"]
    decls = node.get("declarations_defined") or []
    return f"{sid}/{decls[-1]['name']}" if len(decls) > 1 else sid


def build_dot(graph, lib_dir=None, title="") -> str:
    L = [
        "digraph plan {",
        "  compound=true; rankdir=BT; nodesep=0.4; ranksep=0.6;",
        '  graph [fontname="Helvetica", fontsize=14];',
        '  node  [fontname="Helvetica", fontsize=10, style=filled, fillcolor=white];',
        '  edge  [color="#888888"];',
        f'  label="{_esc(title)}"; labelloc=t;',
    ]
    cache: dict = {}
    nodes = graph.topo_sorted()

    for n in nodes:
        sid = n["statement_id"]
        color = _STATUS_COLOR.get(n.get("status"), "#ffffff")
        decls = n.get("declarations_defined") or []
        dd = _decl_deps(n, lib_dir, cache) if len(decls) > 1 else None

        if dd and len(decls) > 1:
            L.append(f'  subgraph "cluster_{sid}" {{')
            L.append(f'    label="{_esc(sid)}  [{n.get("status")}]"; '
                     f'style=filled; fillcolor="{color}"; color="#999999";')
            names = {d["name"] for d in decls}
            for d in decls:
                shp = _DECL_SHAPE.get(d.get("type"), "ellipse")
                L.append(f'    "{sid}/{d["name"]}" [label="{_esc(d["name"])}", shape={shp}];')
            for d, ds in dd.items():
                if d in names:
                    for dep in ds:
                        if dep in names:
                            L.append(f'    "{sid}/{d}" -> "{sid}/{dep}";')
            L.append("  }")
        else:
            shp = "box" if n.get("type") == "Definition" else "ellipse"
            lbl = f'{_esc(sid)}\\n[{n.get("status")}]'
            L.append(f'  "{sid}" [label="{lbl}", shape={shp}, fillcolor="{color}"];')

    # statement-level dependency edges (A depends on B  =>  A -> B)
    from .store import _is_meta
    for n in nodes:
        src = _rep(n)
        for dep in n.get("dependencies") or []:
            dn = graph.get(dep)
            if dn is None or _is_meta(dn):
                continue
            L.append(f'  "{src}" -> "{_rep(dn)}" [penwidth=2, color="#333333"];')

    L.append("}")
    return "\n".join(L)


def render(graph, out_path, lib_dir=None, title="", fmt="png") -> dict:
    dot = build_dot(graph, lib_dir, title)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dot_file = out.with_suffix(".dot")
    dot_file.write_text(dot, encoding="utf-8")
    result = {"dot": str(dot_file), "image": None}
    dotbin = shutil.which("dot")
    if dotbin:
        img = out.with_suffix(f".{fmt}")
        subprocess.run([dotbin, f"-T{fmt}", str(dot_file), "-o", str(img)], check=True)
        result["image"] = str(img)
    return result
