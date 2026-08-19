"""PlanGraph — the Mem0-g–backed authoritative store for the statement plan.

A PlanGraph is bound to a **data folder** (next to the target file). It keeps the
graph in an embedded Qdrant there, and on close auto-writes the derived views
`statements.json` and `progress.json`, plus `analytics.json`, into the same folder —
so all state for a target lives in one place, mirroring the predecessor layout.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import config
from ._vendor.toposort import topologically_sort_statements, find_dependency_cycles
from ._vendor.cone import forward_dependency_cone

COMPLETED_STATES = {"completed", "completed_axiom"}

# "Meta" nodes (an LLM plan summary, informal research notes) are stored + embedded for
# semantic search but excluded from the dependency graph, status dashboard, and
# statements.json export. They form the "informal" group in search results.
META_TYPES = {"Summary", "Note"}


def _is_meta(node: dict) -> bool:
    return node.get("type") in META_TYPES or node.get("kind") == "summary"

NODE_KEYS = [
    "statement_id", "type", "name", "content", "dependencies", "dependents",
    "proof", "anchor", "mathlib_types", "lean_path", "hierarchy_level",
    "corrections", "status", "do_not_import", "declarations_defined",
    "imports", "source_start", "source_end",
]

# Extra provenance fields kept on informal notes (type "Note"): a note is a belief with
# evidence, so it must carry where it came from and how sure we are.
NOTE_KEYS = [
    "confidence", "source", "evidence", "method", "caveats", "related",
    "created", "updated",
]

# statements.json export field policy (matches the original on-disk shape).
_REQUIRED = ["type", "name", "content", "dependencies", "hierarchy_level"]
_OPTIONAL = ["proof", "anchor", "mathlib_types", "lean_path", "corrections"]


def _now() -> str:
    return datetime.now().isoformat()


def _default_node(stmt: dict) -> dict:
    return {
        "statement_id": stmt["id"],
        "type": stmt.get("type", "Theorem"),
        "name": stmt.get("name", ""),
        "content": stmt.get("content", ""),
        "dependencies": list(stmt.get("dependencies") or []),
        "dependents": list(stmt.get("dependents") or []),
        "proof": stmt.get("proof"),
        "anchor": stmt.get("anchor"),
        "mathlib_types": stmt.get("mathlib_types"),
        "lean_path": stmt.get("lean_path"),
        "hierarchy_level": stmt.get("hierarchy_level", 0),
        "corrections": stmt.get("corrections"),
        "status": stmt.get("status", "pending"),
        "do_not_import": list(stmt.get("do_not_import") or []),
        "declarations_defined": list(stmt.get("declarations_defined") or []),
        "imports": list(stmt.get("imports") or []),
        "source_start": stmt.get("source_start"),
        "source_end": stmt.get("source_end"),
    }


def _hit(n: dict, informal: bool = False) -> dict:
    """Shape one search hit for output; informal hits carry their provenance."""
    out = {
        "statement_id": n["statement_id"],
        "name": n.get("name"),
        "type": n.get("type"),
        "status": n.get("status"),
        "embed_score": n.get("_embed_score"),
        "rerank_score": n.get("_rerank_score"),
        "content": n.get("content"),
    }
    if informal:
        out["confidence"] = n.get("confidence")
        out["source"] = n.get("source")
        out["updated"] = n.get("updated") or n.get("created")
    return out


class PlanGraph:
    """Statement-plan store over Mem0, bound to a data folder next to the target."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.mem = config.get_plan_memory(self.data_dir)
        self._id2mid: dict[str, str] = {}
        self._nodes: dict[str, dict] = {}
        self._dirty = False
        self._analytics = self._load_analytics()
        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        ga = self.mem.get_all(filters={"user_id": config.SCOPE}, top_k=100000)
        items = ga.get("results", ga) if isinstance(ga, dict) else ga
        items = sorted(
            items or [],
            key=lambda it: ((it.get("metadata") or {}).get("order", 0),
                            (it.get("metadata") or {}).get("statement_id", "")),
        )
        for it in items:
            md = it.get("metadata") or {}
            sid = md.get("statement_id")
            if not sid:
                continue
            node = dict(md)
            node.setdefault("content", it.get("memory", ""))
            self._id2mid[sid] = it["id"]
            self._nodes[sid] = node

    def _load_analytics(self) -> dict:
        f = self.data_dir / "analytics.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"per_statement": {}, "updated_at": None}

    # ------------------------------------------------------------------ persist
    def persist_views(self) -> None:
        """Write statements.json + progress.json + analytics.json into the data dir."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        data, progress = self.export()
        (self.data_dir / "statements.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.data_dir / "progress.json").write_text(
            json.dumps(progress, indent=2), encoding="utf-8")
        self._analytics["updated_at"] = _now()
        (self.data_dir / "analytics.json").write_text(
            json.dumps(self._analytics, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self) -> None:
        if self._dirty:
            try:
                self.persist_views()
            except Exception:
                pass
        try:
            client = getattr(getattr(self.mem, "vector_store", None), "client", None)
            if client is not None:
                client.close()
        except Exception:
            pass
        try:
            self.mem.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ CRUD
    def add(self, stmt: dict) -> dict:
        sid = stmt["id"]
        if sid in self._id2mid:
            return self.update(sid, **{k: v for k, v in stmt.items() if k != "id"})
        node = _default_node(stmt)
        if stmt.get("type") == "Note":
            node.update({k: stmt[k] for k in NOTE_KEYS if k in stmt})
            node["status"] = "n/a"
            node["dependencies"] = []
            node.setdefault("created", _now())
        node["order"] = max((n.get("order", -1) for n in self._nodes.values()), default=-1) + 1
        res = self.mem.add(node["content"] or sid, user_id=config.SCOPE,
                           metadata=node, infer=False)
        results = res.get("results", res) if isinstance(res, dict) else res
        self._id2mid[sid] = results[0]["id"]
        self._nodes[sid] = node
        if not _is_meta(node):
            self._record_status(sid, node["status"])
        self._dirty = True
        return node

    def get(self, sid: str) -> dict | None:
        return self._nodes.get(sid)

    def all(self) -> list[dict]:
        return list(self._nodes.values())

    def ids(self) -> list[str]:
        return list(self._nodes.keys())

    def _write(self, sid: str) -> dict:
        node = self._nodes[sid]
        node["statement_id"] = sid
        self.mem.update(self._id2mid[sid], data=node.get("content") or sid,
                        metadata=node)
        self._dirty = True
        return node

    def update(self, sid: str, **fields: Any) -> dict:
        node = self._nodes.get(sid)
        if node is None:
            raise KeyError(f"unknown statement {sid!r}")
        fields.pop("id", None)
        fields.pop("statement_id", None)
        node.update(fields)
        if _is_meta(node):
            node["updated"] = _now()
        return self._write(sid)

    def remove_fields(self, sid: str, fields: Iterable[str]) -> dict:
        node = self._nodes.get(sid)
        if node is None:
            raise KeyError(f"unknown statement {sid!r}")
        for f in fields:
            if f not in ("statement_id", "id"):
                node.pop(f, None)
        return self._write(sid)

    def delete(self, sid: str) -> None:
        mid = self._id2mid.pop(sid, None)
        self._nodes.pop(sid, None)
        self._dirty = True
        if mid:
            try:
                self.mem.delete(mid)
            except Exception:
                pass

    # ---------------------------------------------------------------- status
    def set_status(self, sid: str, status: str) -> dict:
        self._record_status(sid, status)
        return self.update(sid, status=status)

    def completed_ids(self) -> list[str]:
        return [sid for sid, n in self._nodes.items()
                if not _is_meta(n) and n.get("status") in COMPLETED_STATES]

    # ---------------------------------------------------------------- analytics
    def _ps(self, sid: str) -> dict:
        return self._analytics["per_statement"].setdefault(
            sid, {"status_history": [], "subagents": []})

    def _record_status(self, sid: str, status: str) -> None:
        self._ps(sid)["status_history"].append({"status": status, "ts": _now()})
        self._dirty = True

    def record_metric(self, sid: str, role: str, data: dict) -> dict:
        entry = {"role": role, "ts": _now(), **(data or {})}
        self._ps(sid)["subagents"].append(entry)
        self._dirty = True
        return entry

    def analytics(self) -> dict:
        return self._analytics

    # ---------------------------------------------------------------- graph
    def _edge_dicts(self) -> list[dict]:
        return [{"id": sid, "dependencies": n.get("dependencies") or []}
                for sid, n in self._nodes.items() if not _is_meta(n)]

    def upsert_summary(self, text: str, name: str = "Plan summary") -> dict:
        """Store/refresh an LLM narrative summary as a searchable meta node (id `Summary`)."""
        return self.add({"id": "Summary", "type": "Summary", "name": name,
                         "content": text, "status": "n/a"})

    def topo_sorted(self) -> list[dict]:
        srt, _ = topologically_sort_statements(self._edge_dicts())
        return [self._nodes[d["id"]] for d in srt]

    def find_cycles(self) -> list[list[str]]:
        return find_dependency_cycles(self._edge_dicts())

    def forward_cone(self, ids: Iterable[str]) -> set[str]:
        return forward_dependency_cone(self._edge_dicts(), set(ids))

    def levels(self) -> dict[str, int]:
        """Dependency layer of each statement: 0 if it has no in-plan deps, else
        1 + max(level of its deps). Statements at the same level are mutually
        independent, so they are safe to formalize in parallel."""
        lvl: dict[str, int] = {}
        for n in self.topo_sorted():  # deps precede dependents; meta excluded
            sid = n["statement_id"]
            deps = [d for d in (n.get("dependencies") or [])
                    if d in self._nodes and not _is_meta(self._nodes[d])]
            lvl[sid] = 0 if not deps else 1 + max((lvl.get(d, 0) for d in deps), default=0)
        return lvl

    def levels_grouped(self) -> dict[int, list[str]]:
        g: dict[int, list[str]] = {}
        for sid, l in self.levels().items():
            g.setdefault(l, []).append(sid)
        return {k: g[k] for k in sorted(g)}

    def recompute_dependents(self) -> None:
        rev: dict[str, list[str]] = {sid: [] for sid in self._nodes}
        for sid, n in self._nodes.items():
            for dep in n.get("dependencies") or []:
                if dep in rev:
                    rev[dep].append(sid)
        for sid, n in self._nodes.items():
            if _is_meta(n):
                continue
            new = sorted(rev[sid])
            if (n.get("dependents") or []) != new:
                self.update(sid, dependents=new)

    # ------------------------------------------------ do_not_import / corrections
    def add_do_not_import(self, sid: str, import_path: str) -> dict:
        node = self._nodes.get(sid)
        if node is None:
            raise KeyError(sid)
        dni = list(node.get("do_not_import") or [])
        if import_path not in dni:
            dni.append(import_path)
        return self.update(sid, do_not_import=dni)

    def clear_do_not_import(self, sid: str) -> dict:
        return self.update(sid, do_not_import=[])

    def load_do_not_import(self) -> list[dict]:
        out = []
        for sid, n in self._nodes.items():
            for ip in n.get("do_not_import") or []:
                out.append({"import_path": ip, "statement_id": sid})
        return out

    def save_corrections(self, sid: str, corrections: list[str]) -> dict:
        return self.update(sid, corrections=list(corrections))

    def load_corrections(self, sid: str) -> list[str] | None:
        n = self._nodes.get(sid)
        return (n or {}).get("corrections")

    # -------------------------------------------------------------- export
    def export(self) -> tuple[dict, dict]:
        """Return (statements_json, progress_json) from the graph, topo-ordered."""
        out = []
        for n in self.topo_sorted():
            s = {"id": n["statement_id"]}
            for k in _REQUIRED:
                s[k] = n.get(k)
            for k in _OPTIONAL:
                v = n.get(k)
                if v not in (None, [], ""):
                    s[k] = v
            out.append(s)
        data = {"statements": out}
        dni = self.load_do_not_import()
        if dni:
            data["do_not_import"] = dni
        return data, {"completed": sorted(self.completed_ids())}

    # -------------------------------------------------------------- semantic
    def search(self, query: str, top_k: int = 5, rerank: bool = True,
               retrieve_k: int | None = None, kind: str = "all") -> dict[str, list[dict]]:
        """Two-stage retrieval (LeanSearch-v2 shape): OpenAI-embedding recall, then an
        OpenAI-LLM cross-encoder rerank per group. Returns
        `{"formal": [...], "informal": [...]}` — formal statement nodes and informal
        notes/summary ranked separately, top_k each. `kind` ("formal"/"informal")
        restricts to one group and skips the other group's rerank call. Set
        rerank=False for pure embedding similarity."""
        pool = retrieve_k or max(top_k * 6, 30)
        sr = self.mem.search(query, filters={"user_id": config.SCOPE}, top_k=pool)
        items = sr.get("results", sr) if isinstance(sr, dict) else sr
        formal: list[dict] = []
        informal: list[dict] = []
        for it in items or []:
            sid = (it.get("metadata") or {}).get("statement_id")
            node = self._nodes.get(sid)
            if node is not None:
                bucket = informal if _is_meta(node) else formal
                bucket.append({**node, "_embed_score": it.get("score")})

        def _ranked(cands: list[dict], instruction: str | None) -> list[dict]:
            if rerank and cands:
                from . import rerank as _rr
                return _rr.rerank(query, cands, top_k, instruction=instruction)
            return cands[:top_k]

        out: dict[str, list[dict]] = {"formal": [], "informal": []}
        if kind in ("all", "formal"):
            out["formal"] = [_hit(n) for n in _ranked(formal, None)]
        if kind in ("all", "informal"):
            from .rerank import NOTE_INSTRUCTION
            out["informal"] = [_hit(n, informal=True)
                               for n in _ranked(informal, NOTE_INSTRUCTION)]
        return out
