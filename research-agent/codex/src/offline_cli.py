"""Local-only command-line backend for MerLEAN's plan graph.

This module is selected explicitly by ``PLAN_OFFLINE=1 scripts/merlean ...``.  Its
commands and output shapes mirror ``plan_store.__main__`` while all authoritative
state stays in ``DATA_DIR/.merlean-offline.json`` and materialized JSON views.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import portalocker

from plan_store import dashboard, lean_sync, prove, visualize
from plan_store.offline_store import (
    OfflinePlanGraph,
    STORE_NAME,
    STORE_VERSION,
    VALID_STATUSES,
    _atomic_json,
    _is_meta,
    import_statements_json,
)


def _out(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _data_dir_for(target) -> Path:
    target = Path(target)
    if target.name == "datas" or target.name.endswith("_data"):
        return target
    if target.suffix == ".lean" or (target.exists() and target.is_file()):
        return target.parent / f"{target.stem}_data"
    legacy = target / "datas"
    if legacy.exists():
        return legacy
    return target / f"{target.name}_data"


def _validate_reset_target(path: Path) -> Path:
    """Reject broad, linked, or unrelated targets; return a canonical deletion path."""
    lexical = path.expanduser().absolute()
    for component in [lexical, *lexical.parents]:
        if component.is_symlink():
            raise ValueError(
                f"refusing to reset through symbolic-link component: {component}"
            )
    resolved = lexical.resolve(strict=False)
    # Delete through this canonical path.  The tests canonicalize macOS's system
    # /var alias; arbitrary user-supplied link ancestors remain forbidden above.
    for component in [resolved, *resolved.parents]:
        if component.is_symlink():
            raise ValueError(
                f"refusing to reset through symbolic-link component: {component}"
            )
    forbidden = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
    plugin_root = Path(__file__).resolve().parent.parent
    forbidden.add(plugin_root.resolve())
    if resolved in forbidden:
        raise ValueError(f"refusing to reset protected path: {resolved}")
    if path.name != "datas" and not path.name.endswith("_data"):
        raise ValueError("reset target must be named 'datas' or end in '_data'")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("reset target exists but is not a directory")
    if not resolved.exists():
        return resolved
    entries = {entry.name for entry in resolved.iterdir()}
    if not entries:
        return resolved

    authoritative = False
    offline_store = resolved / STORE_NAME
    if offline_store.is_file():
        try:
            saved = json.loads(offline_store.read_text(encoding="utf-8"))
            authoritative = (
                saved.get("version") == STORE_VERSION
                and isinstance(saved.get("nodes"), list)
            )
        except (OSError, ValueError, AttributeError):
            authoritative = False
    statements = resolved / "statements.json"
    if statements.is_file():
        try:
            saved = json.loads(statements.read_text(encoding="utf-8"))
            statement_list = saved.get("statements") if isinstance(saved, dict) else saved
            valid_statements = (
                isinstance(statement_list, list)
                and all(
                    isinstance(statement, dict)
                    and isinstance(statement.get("id"), str)
                    and bool(statement["id"])
                    and isinstance(statement.get("dependencies", []), list)
                    for statement in statement_list
                )
            )
            authoritative = authoritative or valid_statements
        except (OSError, ValueError):
            pass
    authoritative = authoritative or (
        (resolved / "qdrant").is_dir() and (resolved / "history.db").is_file()
    )
    if not authoritative:
        raise ValueError(
            "refusing to reset a non-empty directory with no valid MerLEAN store"
        )
    # Enumerate the complete deletion set without following links.  A plan directory
    # should be self-contained; links to user data are never valid reset targets.
    for parent, dirnames, filenames in os.walk(resolved, followlinks=False):
        for name in [*dirnames, *filenames]:
            candidate = Path(parent) / name
            if candidate.is_symlink():
                raise ValueError(
                    f"refusing to reset a plan containing symbolic link: {candidate}"
                )
    allowed_exact = {
        STORE_NAME, "statements.json", "progress.json", "analytics.json",
        "corrections.json", "history.db", "qdrant", "summary.md",
    }
    allowed_graph_suffixes = {".dot", ".png", ".svg", ".pdf", ".jpg", ".jpeg", ".webp"}
    unexpected = sorted(
        name for name in entries
        if name not in allowed_exact
        and not (name.startswith("graph") and Path(name).suffix.lower() in allowed_graph_suffixes)
    )
    if unexpected:
        raise ValueError(
            "refusing to reset a plan directory containing unexpected entries: "
            + ", ".join(unexpected)
        )
    return resolved


def _plan_lock(data_dir: Path) -> portalocker.Lock:
    """One transaction lock shared by all offline CLI processes for this data dir."""
    parent = data_dir.expanduser().absolute().parent
    parent.mkdir(parents=True, exist_ok=True)
    lock_path = parent / f".{data_dir.name}.merlean.lock"
    return portalocker.Lock(str(lock_path), mode="a", timeout=120)


def _offline_summary(graph: OfflinePlanGraph, name: str) -> dict:
    nodes = graph.topo_sorted()
    total = len(nodes)
    completed = [
        node for node in nodes
        if node.get("status") in {"completed", "completed_axiom"}
    ]
    pending = [node for node in nodes if node not in completed]
    roots = [node for node in nodes if not (node.get("dependencies") or [])]
    leaves = []
    depended_on = {
        dep for node in nodes for dep in (node.get("dependencies") or [])
    }
    for node in nodes:
        if node["statement_id"] not in depended_on:
            leaves.append(node)

    def labels(items: list[dict]) -> str:
        return ", ".join(node["statement_id"] for node in items) or "none"

    level_lines = []
    for level, sids in graph.levels_grouped().items():
        level_lines.append(f"- Level {level}: {', '.join(sids)}")
    architecture = "\n".join(level_lines) or "- No formal statements yet."
    text = (
        f"# {name or 'Plan'} — summary\n\n"
        "## Overview\n\n"
        f"This plan contains {total} formal statement(s). Dependency roots: "
        f"{labels(roots)}. Final downstream statement(s): {labels(leaves)}.\n\n"
        "## Proof architecture\n\n"
        f"{architecture}\n\n"
        "## Status\n\n"
        f"Completed: {len(completed)}/{total} ({labels(completed)}). "
        f"Not completed: {len(pending)} ({labels(pending)}).\n"
    )
    graph.upsert_summary(text)
    output = graph.data_dir / "summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return {"summary": text, "summary_md": str(output), "node": "Summary", "chars": len(text)}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="plan_store (offline)")
    parser.add_argument(
        "--data", default=None,
        help="the data folder (…/<file>_data); derived from FILE for seed-sorries",
    )
    commands = parser.add_subparsers(dest="cmd", required=True)

    p = commands.add_parser("seed-sorries"); p.add_argument("file"); p.add_argument("--lib-dir", required=True)
    p = commands.add_parser("import-json"); p.add_argument("path")
    p = commands.add_parser("export-json"); p.add_argument("--out", default=None)
    p = commands.add_parser("list"); p.add_argument("--status", default=None)
    p.add_argument("--kind", choices=["formal", "informal", "all"], default="all")
    p = commands.add_parser("get"); p.add_argument("sid")
    commands.add_parser("topo")
    p = commands.add_parser("cone"); p.add_argument("sids", nargs="+")
    commands.add_parser("cycles")
    commands.add_parser("levels")
    p = commands.add_parser("set-status"); p.add_argument("sid"); p.add_argument("status")
    p = commands.add_parser("update"); p.add_argument("sid"); p.add_argument("--json", required=True, dest="payload")
    p = commands.add_parser("add"); p.add_argument("--json", required=True, dest="payload")
    p = commands.add_parser("delete"); p.add_argument("sid")
    p = commands.add_parser("sync-lean"); p.add_argument("lib_dir")
    p = commands.add_parser("reconcile"); p.add_argument("lib_dir"); p.add_argument("--build", action="store_true")
    commands.add_parser("lint")
    p = commands.add_parser("record"); p.add_argument("sid"); p.add_argument("--role", required=True); p.add_argument("--json", default="{}", dest="payload")
    p = commands.add_parser("analytics"); p.add_argument("--plain", action="store_true")
    commands.add_parser("status")
    commands.add_parser("summarize")
    p = commands.add_parser("search"); p.add_argument("query"); p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--no-rerank", action="store_true"); p.add_argument("--retrieve-k", type=int, default=None)
    p.add_argument("--kind", choices=["formal", "informal", "all"], default="all")
    p = commands.add_parser("visualize"); p.add_argument("--lib-dir", default=None); p.add_argument("--out", default=None); p.add_argument("--format", default="png")
    commands.add_parser("reset")

    args = parser.parse_args(argv)
    if args.cmd == "seed-sorries":
        data_dir = Path(args.data) if args.data else _data_dir_for(args.file)
    else:
        if not args.data:
            parser.error(f"--data <folder> is required for '{args.cmd}'")
        data_dir = Path(args.data)

    lock = _plan_lock(data_dir)
    lock.acquire()
    if args.cmd == "reset":
        try:
            try:
                reset_target = _validate_reset_target(data_dir)
            except ValueError as exc:
                parser.error(str(exc))
            if reset_target.exists():
                shutil.rmtree(reset_target)
            _out({"ok": True, "reset": str(data_dir)})
        finally:
            lock.release()
        return

    try:
        graph = OfflinePlanGraph(data_dir)
    except BaseException:
        lock.release()
        raise
    try:
        if args.cmd == "seed-sorries":
            node = prove.seed_sorry_file(graph, args.file, args.lib_dir)
            _out({"data_dir": str(data_dir), "node": node} if node else {
                "data_dir": str(data_dir), "error": "no sorry/admit declarations found",
            })
        elif args.cmd == "import-json":
            count = import_statements_json(graph, args.path)
            _out({"imported": count, "ids": graph.ids(), "data_dir": str(data_dir)})
        elif args.cmd == "export-json":
            data, progress = graph.export()
            output = Path(args.out) if args.out else data_dir / "statements.json"
            _atomic_json(output, data)
            _atomic_json(output.parent / "progress.json", progress)
            _out({"wrote": str(output), "n": len(data["statements"])})
        elif args.cmd == "list":
            nodes = graph.all()
            if args.kind != "all":
                nodes = [
                    node for node in nodes
                    if _is_meta(node) == (args.kind == "informal")
                ]
            if args.status:
                nodes = [node for node in nodes if node.get("status") == args.status]
            _out([
                {
                    "id": node["statement_id"], "type": node.get("type"),
                    "name": node.get("name"), "status": node.get("status"),
                    "dependencies": node.get("dependencies"),
                    **({"confidence": node["confidence"]} if node.get("confidence") else {}),
                }
                for node in nodes
            ])
        elif args.cmd == "get":
            node = graph.get(args.sid)
            _out(node if node is not None else {"error": f"unknown {args.sid}"})
        elif args.cmd == "topo":
            _out([node["statement_id"] for node in graph.topo_sorted()])
        elif args.cmd == "cone":
            _out(sorted(graph.forward_cone(args.sids)))
        elif args.cmd == "cycles":
            _out(graph.find_cycles())
        elif args.cmd == "levels":
            grouped = graph.levels_grouped()
            _out({
                str(level): [
                    {
                        "id": sid, "status": graph.get(sid).get("status"),
                        "name": graph.get(sid).get("name"),
                    }
                    for sid in grouped[level]
                ]
                for level in grouped
            })
        elif args.cmd == "set-status":
            if args.status not in VALID_STATUSES:
                parser.error(
                    f"invalid status {args.status!r}; expected one of "
                    f"{', '.join(sorted(VALID_STATUSES))}"
                )
            _out(graph.set_status(args.sid, args.status))
        elif args.cmd == "update":
            _out(graph.update(args.sid, **json.loads(args.payload)))
        elif args.cmd == "add":
            _out(graph.add(json.loads(args.payload)))
        elif args.cmd == "delete":
            graph.delete(args.sid)
            _out({"deleted": args.sid})
        elif args.cmd == "sync-lean":
            synced = lean_sync.sync_edges_from_lean(graph, args.lib_dir)
            _out({"synced": synced, "cycles": graph.find_cycles()})
        elif args.cmd == "reconcile":
            changes = lean_sync.reconcile_status_from_lean(
                graph, args.lib_dir, build=args.build,
            )
            _out({"changes": changes, "n": len(changes)})
        elif args.cmd == "lint":
            _out(lean_sync.lint_declarations(graph))
        elif args.cmd == "record":
            _out(graph.record_metric(args.sid, args.role, json.loads(args.payload)))
        elif args.cmd == "analytics":
            if args.plain:
                print(dashboard.render_analytics(graph, data_dir.name))
            else:
                _out(graph.analytics())
        elif args.cmd == "status":
            print(dashboard.render_status(graph, data_dir.name))
        elif args.cmd == "summarize":
            result = _offline_summary(graph, data_dir.name)
            print(result["summary"])
            print(f"\n[saved to {result['summary_md']} · searchable as node '{result['node']}']")
        elif args.cmd == "search":
            _out(graph.search(
                args.query, top_k=args.top_k, rerank=not args.no_rerank,
                retrieve_k=args.retrieve_k, kind=args.kind,
            ))
        elif args.cmd == "visualize":
            output = args.out or str(data_dir / "graph")
            result = visualize.render(
                graph, output, lib_dir=args.lib_dir,
                title=f"plan graph: {data_dir.name}", fmt=args.format,
            )
            _out(result)
    finally:
        try:
            graph.close()
        finally:
            lock.release()


if __name__ == "__main__":
    main(sys.argv[1:])
