"""Phase 1 verification — run with the shared venv python from the repo root:

    .venv/bin/python src/plan_store/tests/verify_phase1.py

Checks (synthetic fixture, no Lean toolchain needed):
  1. import-json -> export-json round-trips statement fields
  2. topo == vendored topologically_sort_statements
  3. cone == vendored forward_dependency_cone
  4. status/progress: completed_ids reproduces progress.json
  5. sync-lean rewrites edges to the REAL Lean deps (graph == Lean dep graph)
  6. semantic search returns the right node in the formal group
  7. informal notes: add/round-trip, excluded from graph/export/sync, searchable in the
     informal group only, update stamps + corrections, delete
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from plan_store import config, compat, lean_sync          # noqa: E402
from plan_store.store import PlanGraph                      # noqa: E402
from plan_store._vendor.toposort import topologically_sort_statements  # noqa: E402
from plan_store._vendor.cone import forward_dependency_cone            # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
DATA = Path(__file__).resolve().parent / "_verify_data"

_fail = 0
def check(name, cond, detail=""):
    global _fail
    mark = "PASS" if cond else "FAIL"
    if not cond:
        _fail += 1
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not cond else ""))


def main():
    # clean slate
    if DATA.exists():
        shutil.rmtree(DATA, ignore_errors=True)

    raw = json.loads((FIX / "statements.json").read_text(encoding="utf-8"))["statements"]

    g = PlanGraph(DATA)
    try:
        # 1. import
        n = compat.import_statements_json(g, FIX / "statements.json")
        check("import count", n == 3, f"got {n}")
        check("ids present", set(g.ids()) == {"Def_DiscreteTorus", "Lem_TorusCard", "Thm_Main"})

        # 2. round-trip export
        data, progress = compat.export_statements_json(g)
        exp = {s["id"]: s for s in data["statements"]}
        rt_ok = True
        for s in raw:
            e = exp.get(s["id"], {})
            for k in ("type", "name", "content", "dependencies", "hierarchy_level"):
                if e.get(k) != s.get(k):
                    rt_ok = False
            if s.get("proof") not in (None, "") and e.get("proof") != s.get("proof"):
                rt_ok = False
        check("export round-trips fields", rt_ok)

        # 3. topo == vendored
        want_topo = [s["id"] for s in topologically_sort_statements(
            [{"id": s["id"], "dependencies": s["dependencies"]} for s in raw])[0]]
        got_topo = [n["statement_id"] for n in g.topo_sorted()]
        check("topo == vendored", got_topo == want_topo, f"{got_topo} vs {want_topo}")

        # 4. cone == vendored (pre-sync edges)
        edge_dicts = [{"id": s["id"], "dependencies": s["dependencies"]} for s in raw]
        want_cone = forward_dependency_cone(edge_dicts, {"Def_DiscreteTorus"})
        got_cone = g.forward_cone(["Def_DiscreteTorus"])
        check("cone == vendored", got_cone == want_cone, f"{sorted(got_cone)} vs {sorted(want_cone)}")
        check("cone is downstream", got_cone == {"Def_DiscreteTorus", "Lem_TorusCard", "Thm_Main"})

        # 5. progress / status
        check("completed_ids == progress.json", g.completed_ids() == ["Def_DiscreteTorus"],
              str(g.completed_ids()))

        # 6. pre-sync: Thm_Main is missing the Lem_TorusCard edge (by design)
        check("pre-sync Thm deps incomplete",
              g.get("Thm_Main")["dependencies"] == ["Def_DiscreteTorus"])

        # 7. sync-lean: rewrite edges from the real .lean files
        lean_sync.sync_edges_from_lean(g, FIX / "lib")
        REAL = {
            "Def_DiscreteTorus": [],
            "Lem_TorusCard": ["Def_DiscreteTorus"],
            "Thm_Main": ["Def_DiscreteTorus", "Lem_TorusCard"],
        }
        edges_ok = all(g.get(sid)["dependencies"] == deps for sid, deps in REAL.items())
        check("graph == real Lean dep graph", edges_ok,
              {sid: g.get(sid)["dependencies"] for sid in REAL})
        check("Thm edge reconciled (added Lem_TorusCard)",
              "Lem_TorusCard" in g.get("Thm_Main")["dependencies"])
        # reverse edges
        check("dependents reversed",
              g.get("Def_DiscreteTorus")["dependents"] == ["Lem_TorusCard", "Thm_Main"],
              str(g.get("Def_DiscreteTorus")["dependents"]))
        # Lean node detail captured
        defs_main = [d["name"] for d in g.get("Thm_Main")["declarations_defined"]]
        check("declarations_defined captured", "Main" in defs_main, str(defs_main))
        check("imports captured",
              "Torusdemo.Lem_TorusCard" in g.get("Thm_Main")["imports"],
              str(g.get("Thm_Main")["imports"]))
        check("no cycles", g.find_cycles() == [])

        # 8. semantic search (two-group output)
        hits = g.search("how many elements does the torus have", top_k=3)
        formal = hits.get("formal", [])
        top = formal[0]["statement_id"] if formal else None
        check("semantic search finds cardinality lemma", top == "Lem_TorusCard", f"top={top}")

        # 9. informal notes
        g.add({"id": "Note_TorusEnum", "type": "Note", "name": "torus enumeration finding",
               "content": "Exhaustive enumeration confirms the 2D discrete torus on Z/5 x Z/5 "
                          "has exactly 25 elements; no smaller counterexample exists.",
               "confidence": "high", "source": "explore: torus cardinality sweep",
               "evidence": "direct product count", "method": "exhaustive enumeration n<=5",
               "related": ["Lem_TorusCard"]})
        note = g.get("Note_TorusEnum")
        check("note round-trips provenance",
              note is not None and note.get("confidence") == "high"
              and note.get("source") == "explore: torus cardinality sweep"
              and bool(note.get("created")), str(note))
        check("note excluded from topo",
              "Note_TorusEnum" not in [n["statement_id"] for n in g.topo_sorted()])
        data2, _ = g.export()
        check("note excluded from export",
              "Note_TorusEnum" not in {s["id"] for s in data2["statements"]})
        check("note excluded from completed_ids", "Note_TorusEnum" not in g.completed_ids())
        synced = lean_sync.sync_edges_from_lean(g, FIX / "lib")
        check("sync-lean skips the note", "Note_TorusEnum" not in synced,
              str(sorted(synced)))
        check("note fields survive sync",
              g.get("Note_TorusEnum").get("confidence") == "high")
        hits2 = g.search("is there a small counterexample to the torus cardinality", top_k=3)
        inf_ids = [h["statement_id"] for h in hits2.get("informal", [])]
        for_ids = [h["statement_id"] for h in hits2.get("formal", [])]
        check("note found in informal group", "Note_TorusEnum" in inf_ids, str(hits2))
        check("note absent from formal group", "Note_TorusEnum" not in for_ids, str(for_ids))
        g.update("Note_TorusEnum", confidence="medium",
                 corrections=["was high; downgraded in the test"])
        note = g.get("Note_TorusEnum")
        check("note update stamps + keeps corrections",
              note.get("confidence") == "medium" and bool(note.get("updated"))
              and note.get("corrections") == ["was high; downgraded in the test"], str(note))
        g.delete("Note_TorusEnum")
        check("note deleted", g.get("Note_TorusEnum") is None
              and "Note_TorusEnum" not in g.ids())
    finally:
        g.close()

    print()
    if _fail:
        print(f"VERIFY: {_fail} check(s) FAILED")
        sys.exit(1)
    print("VERIFY: all checks PASSED")


if __name__ == "__main__":
    main()
