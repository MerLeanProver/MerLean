"""plan_store CLI — the boundary the Claude Code skills shell out to.

All state for a target lives in a data folder NEXT TO the target file
(`<file>_data/`), passed as `--data <folder>`. `seed-sorries` derives that folder
from the file. The graph is auto-exported to `statements.json` / `progress.json` and
analytics to `analytics.json` in that folder.

Usage:
  python <cli> --data <DATA_DIR> <command> [...]

Commands:
  seed-sorries FILE [--lib-dir D]  seed a Lean file's sorries (derives DATA from FILE)
  import-json PATH                 load a statements.json (+ progress/corrections)
  export-json [--out P]            write statements.json + progress.json (default: into DATA)
  list [--status S] [--kind K]     list nodes (K: formal | informal | all)
  get SID                          print one node
  topo                             ids in dependency order
  cone SID [SID...]                forward (downstream) cone
  cycles                           dependency cycles
  set-status SID STATUS            set status (auto-recorded in analytics)
  update SID --json '{}'           merge fields
  add --json '{...}'               add a node (formal statement, or an informal Note)
  delete SID                       delete a node
  sync-lean LIB_DIR                rewrite edges from real .lean files
  reconcile LIB_DIR [--build]      re-derive status from .lean files (self-heal Mem0 status drift)
  lint                             flag top-level decl names defined by >1 node (run after sync-lean)
  record SID --role R --json '{}'  append a subagent metric to analytics.json
  analytics                        print analytics.json
  search QUERY [--top-k N] [--kind K]  semantic search -> {"formal": [...], "informal": [...]}
  visualize [--lib-dir D] [--out P] [--format F]   render the graph (default: into DATA)
  reset                            wipe the DATA folder

Output is JSON on stdout.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import config
from .store import PlanGraph, _is_meta
from . import compat, lean_sync, prove, visualize, dashboard, summary


def _out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plan_store")
    ap.add_argument("--data", default=None, help="the data folder (…/<file>_data); "
                                                 "derived from FILE for seed-sorries")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seed-sorries"); p.add_argument("file"); p.add_argument("--lib-dir", required=True)
    p = sub.add_parser("import-json"); p.add_argument("path")
    p = sub.add_parser("export-json"); p.add_argument("--out", default=None)
    p = sub.add_parser("list"); p.add_argument("--status", default=None)
    p.add_argument("--kind", choices=["formal", "informal", "all"], default="all")
    p = sub.add_parser("get"); p.add_argument("sid")
    sub.add_parser("topo")
    p = sub.add_parser("cone"); p.add_argument("sids", nargs="+")
    sub.add_parser("cycles")
    sub.add_parser("levels")
    p = sub.add_parser("set-status"); p.add_argument("sid"); p.add_argument("status")
    p = sub.add_parser("update"); p.add_argument("sid"); p.add_argument("--json", required=True, dest="payload")
    p = sub.add_parser("add"); p.add_argument("--json", required=True, dest="payload")
    p = sub.add_parser("delete"); p.add_argument("sid")
    p = sub.add_parser("sync-lean"); p.add_argument("lib_dir")
    p = sub.add_parser("reconcile"); p.add_argument("lib_dir"); p.add_argument("--build", action="store_true")
    sub.add_parser("lint")
    p = sub.add_parser("record"); p.add_argument("sid"); p.add_argument("--role", required=True); p.add_argument("--json", default="{}", dest="payload")
    p = sub.add_parser("analytics"); p.add_argument("--plain", action="store_true")
    sub.add_parser("status")
    sub.add_parser("summarize")
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--no-rerank", action="store_true"); p.add_argument("--retrieve-k", type=int, default=None)
    p.add_argument("--kind", choices=["formal", "informal", "all"], default="all")
    p = sub.add_parser("visualize"); p.add_argument("--lib-dir", default=None); p.add_argument("--out", default=None); p.add_argument("--format", default="png")
    sub.add_parser("reset")

    args = ap.parse_args(argv)

    # Resolve the data folder.
    if args.cmd == "seed-sorries":
        data_dir = Path(args.data) if args.data else config.get_data_dir(args.file)
    else:
        if not args.data:
            ap.error(f"--data <folder> is required for '{args.cmd}'")
        data_dir = Path(args.data)

    if args.cmd == "reset":
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
        _out({"ok": True, "reset": str(data_dir)})
        return

    graph = PlanGraph(data_dir)
    try:
        if args.cmd == "seed-sorries":
            node = prove.seed_sorry_file(graph, args.file, args.lib_dir)
            _out({"data_dir": str(data_dir), "node": node} if node
                 else {"data_dir": str(data_dir), "error": "no sorry/admit declarations found"})
        elif args.cmd == "import-json":
            n = compat.import_statements_json(graph, args.path)
            _out({"imported": n, "ids": graph.ids(), "data_dir": str(data_dir)})
        elif args.cmd == "export-json":
            data, progress = graph.export()
            outp = Path(args.out) if args.out else data_dir / "statements.json"
            outp.parent.mkdir(parents=True, exist_ok=True)
            outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            (outp.parent / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
            _out({"wrote": str(outp), "n": len(data["statements"])})
        elif args.cmd == "list":
            nodes = graph.all()
            if args.kind != "all":
                nodes = [n for n in nodes if _is_meta(n) == (args.kind == "informal")]
            if args.status:
                nodes = [n for n in nodes if n.get("status") == args.status]
            _out([{"id": n["statement_id"], "type": n.get("type"), "name": n.get("name"),
                   "status": n.get("status"), "dependencies": n.get("dependencies"),
                   **({"confidence": n["confidence"]} if n.get("confidence") else {})}
                  for n in nodes])
        elif args.cmd == "get":
            node = graph.get(args.sid)
            _out(node if node is not None else {"error": f"unknown {args.sid}"})
        elif args.cmd == "topo":
            _out([n["statement_id"] for n in graph.topo_sorted()])
        elif args.cmd == "cone":
            _out(sorted(graph.forward_cone(args.sids)))
        elif args.cmd == "cycles":
            _out(graph.find_cycles())
        elif args.cmd == "levels":
            grouped = graph.levels_grouped()
            _out({str(k): [{"id": sid, "status": graph.get(sid).get("status"),
                            "name": graph.get(sid).get("name")} for sid in grouped[k]]
                  for k in grouped})
        elif args.cmd == "set-status":
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
            changes = lean_sync.reconcile_status_from_lean(graph, args.lib_dir, build=args.build)
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
            res = summary.summarize(graph, data_dir, name=data_dir.name)
            print(res["summary"])
            print(f"\n[saved to {res['summary_md']} · searchable as node '{res['node']}']")
        elif args.cmd == "search":
            _out(graph.search(args.query, top_k=args.top_k, rerank=not args.no_rerank,
                              retrieve_k=args.retrieve_k, kind=args.kind))
        elif args.cmd == "visualize":
            out = args.out or str(data_dir / "graph")
            res = visualize.render(graph, out, lib_dir=args.lib_dir,
                                   title=f"plan graph: {data_dir.name}", fmt=args.format)
            _out(res)
    finally:
        graph.close()


if __name__ == "__main__":
    main(sys.argv[1:])
