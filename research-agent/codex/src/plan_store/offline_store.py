"""Deterministic, local-only plan graph used when ``PLAN_OFFLINE=1``.

The online :class:`plan_store.store.PlanGraph` remains the default.  This store mirrors
its public interface closely enough for every MerLEAN mode, but persists ordinary JSON
inside the target data directory and never constructs an embedder, vector database, or
LLM client.  Search is deliberately lexical and deterministic.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ._vendor.cone import forward_dependency_cone
from ._vendor.toposort import find_dependency_cycles, topologically_sort_statements


COMPLETED_STATES = {"completed", "completed_axiom"}
VALID_STATUSES = {"pending", "in_progress", "completed", "completed_axiom", "failed"}
META_TYPES = {"Summary", "Note"}
STORE_NAME = ".merlean-offline.json"
STORE_VERSION = 1

NODE_KEYS = [
    "statement_id", "type", "name", "content", "dependencies", "dependents",
    "proof", "anchor", "mathlib_types", "lean_path", "hierarchy_level",
    "corrections", "status", "do_not_import", "declarations_defined",
    "imports", "source_start", "source_end",
]
NOTE_KEYS = [
    "confidence", "source", "evidence", "method", "caveats", "related",
    "created", "updated",
]
_REQUIRED = ["type", "name", "content", "dependencies", "hierarchy_level"]
_OPTIONAL = ["proof", "anchor", "mathlib_types", "lean_path", "corrections"]


def _now() -> str:
    return datetime.now().isoformat()


def _is_meta(node: dict) -> bool:
    return node.get("type") in META_TYPES or node.get("kind") == "summary"


def _default_node(stmt: dict) -> dict:
    sid = stmt.get("id", stmt.get("statement_id"))
    if not sid:
        raise KeyError("node payload requires a non-empty 'id'")
    is_meta = _is_meta(stmt)
    status = stmt.get("status", "n/a" if is_meta else "pending")
    if (is_meta and status != "n/a") or (not is_meta and status not in VALID_STATUSES):
        expected = "'n/a'" if is_meta else str(sorted(VALID_STATUSES))
        raise ValueError(f"invalid status {status!r}; expected {expected}")
    return {
        "statement_id": sid,
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
        "status": status,
        "do_not_import": list(stmt.get("do_not_import") or []),
        "declarations_defined": list(stmt.get("declarations_defined") or []),
        "imports": list(stmt.get("imports") or []),
        "source_start": stmt.get("source_start"),
        "source_end": stmt.get("source_end"),
    }


def _atomic_json(path: Path, value: Any) -> None:
    """Atomically replace one JSON file without ever writing outside ``path.parent``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _terms(value: Any) -> list[str]:
    """Tokenize identifiers and prose reproducibly, including snake/camel case parts."""
    text = str(value or "")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).lower()
    raw = re.findall(r"[a-z0-9]+", text.replace("_", " "))
    return [token for token in raw if token]


def _lexical_score(query: str, node: dict) -> float:
    """Weighted query coverage + Jaccard + exact-phrase bonus in ``[0, 1]``."""
    q = Counter(_terms(query))
    if not q:
        return 0.0

    all_document_terms: list[str] = []
    best_weight = {term: 0 for term in q}
    for field, weight in (
        ("statement_id", 4), ("name", 4), ("type", 1), ("content", 3),
        ("anchor", 2), ("proof", 1), ("mathlib_types", 2), ("source", 1),
        ("evidence", 1), ("method", 1), ("caveats", 1), ("related", 1),
        ("dependencies", 1),
    ):
        field_terms = _terms(node.get(field))
        all_document_terms.extend(field_terms)
        field_counts = Counter(field_terms)
        for term, query_count in q.items():
            if min(query_count, field_counts.get(term, 0)):
                best_weight[term] = max(best_weight[term], weight)
    max_field_weight = 4
    weighted_overlap = sum(q[term] * best_weight[term] for term in q)
    coverage = weighted_overlap / max(sum(q.values()) * max_field_weight, 1)
    d = Counter(all_document_terms)
    qset, dset = set(q), set(d)
    jaccard = len(qset & dset) / max(len(qset | dset), 1)
    phrase = " ".join(_terms(query))
    document = " ".join(_terms(" ".join(str(node.get(k) or "") for k in (
        "statement_id", "name", "content", "anchor", "source", "evidence"))))
    phrase_bonus = 1.0 if phrase and phrase in document else 0.0
    return round(min(1.0, 0.75 * coverage + 0.20 * jaccard + 0.05 * phrase_bonus), 6)


def _hit(node: dict, score: float, informal: bool = False) -> dict:
    out = {
        "statement_id": node["statement_id"],
        "name": node.get("name"),
        "type": node.get("type"),
        "status": node.get("status"),
        # Keep the online result schema.  In offline mode this is a lexical score.
        "embed_score": score,
        "rerank_score": None,
        "content": node.get("content"),
    }
    if informal:
        out["confidence"] = node.get("confidence")
        out["source"] = node.get("source")
        out["updated"] = node.get("updated") or node.get("created")
    return out


class OfflinePlanGraph:
    """JSON-backed implementation of the plan graph's public operations."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.store_path = self.data_dir / STORE_NAME
        self._nodes: dict[str, dict] = {}
        self._dirty = False
        self._analytics = self._load_analytics()
        if self.store_path.exists():
            self._load_store()
        elif (self.data_dir / "statements.json").exists():
            self._bootstrap_views()

    # ---------------------------------------------------------------- load/persist
    def _load_analytics(self) -> dict:
        path = self.data_dir / "analytics.json"
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    value.setdefault("per_statement", {})
                    value.setdefault("updated_at", None)
                    return value
            except (OSError, ValueError):
                pass
        return {"per_statement": {}, "updated_at": None}

    def _load_store(self) -> None:
        raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        if raw.get("version") != STORE_VERSION:
            raise ValueError(
                f"unsupported offline store version {raw.get('version')!r}; "
                f"expected {STORE_VERSION}"
            )
        for position, saved in enumerate(raw.get("nodes") or []):
            node = dict(saved)
            sid = node.get("statement_id")
            if not sid:
                continue
            node.setdefault("order", position)
            self._nodes[sid] = node

    def _bootstrap_views(self) -> None:
        """Recover formal nodes from materialized online views after an API outage."""
        path = self.data_dir / "statements.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        statements = raw.get("statements", raw) if isinstance(raw, dict) else raw
        completed: set[str] = set()
        progress = self.data_dir / "progress.json"
        if progress.exists():
            completed = set(json.loads(progress.read_text(encoding="utf-8")).get("completed", []))
        corrections: dict[str, Any] = {}
        corrections_path = self.data_dir / "corrections.json"
        if corrections_path.exists():
            corrections = json.loads(corrections_path.read_text(encoding="utf-8"))
        dni: dict[str, list[str]] = {}
        if isinstance(raw, dict):
            for entry in raw.get("do_not_import", []) or []:
                sid, import_path = entry.get("statement_id"), entry.get("import_path")
                if sid and import_path:
                    dni.setdefault(sid, []).append(import_path)
        for statement in statements or []:
            item = dict(statement)
            sid = item["id"]
            item["status"] = "completed" if sid in completed else "pending"
            if sid in corrections:
                item["corrections"] = corrections[sid]
            if sid in dni:
                item["do_not_import"] = dni[sid]
            self.add(item)

    def persist_views(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self._nodes.values(), key=lambda n: (n.get("order", 0), n["statement_id"]))
        _atomic_json(self.store_path, {"version": STORE_VERSION, "nodes": ordered})
        statements, progress = self.export()
        _atomic_json(self.data_dir / "statements.json", statements)
        _atomic_json(self.data_dir / "progress.json", progress)
        self._analytics["updated_at"] = _now()
        _atomic_json(self.data_dir / "analytics.json", self._analytics)
        self._dirty = False

    def close(self) -> None:
        if self._dirty:
            self.persist_views()

    # ---------------------------------------------------------------- CRUD
    def add(self, stmt: dict) -> dict:
        sid = stmt.get("id", stmt.get("statement_id"))
        if not sid:
            raise KeyError("node payload requires a non-empty 'id'")
        if sid in self._nodes:
            return self.update(sid, **{
                key: value for key, value in stmt.items()
                if key not in {"id", "statement_id"}
            })
        node = _default_node(stmt)
        if stmt.get("type") == "Note":
            node.update({key: stmt[key] for key in NOTE_KEYS if key in stmt})
            node["status"] = "n/a"
            node["dependencies"] = []
            node.setdefault("created", _now())
        node["order"] = max((n.get("order", -1) for n in self._nodes.values()), default=-1) + 1
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

    def update(self, sid: str, **fields: Any) -> dict:
        node = self._nodes.get(sid)
        if node is None:
            raise KeyError(f"unknown statement {sid!r}")
        fields.pop("id", None)
        fields.pop("statement_id", None)
        candidate = {**node, **fields}
        candidate_status = candidate.get("status", "n/a" if _is_meta(candidate) else "pending")
        if (_is_meta(candidate) and candidate_status != "n/a") or (
            not _is_meta(candidate) and candidate_status not in VALID_STATUSES
        ):
            expected = "'n/a'" if _is_meta(candidate) else str(sorted(VALID_STATUSES))
            raise ValueError(f"invalid status {candidate_status!r}; expected {expected}")
        node.update(fields)
        if _is_meta(node):
            node["updated"] = _now()
        self._dirty = True
        return node

    def remove_fields(self, sid: str, fields: Iterable[str]) -> dict:
        node = self._nodes.get(sid)
        if node is None:
            raise KeyError(f"unknown statement {sid!r}")
        for field in fields:
            if field not in {"statement_id", "id"}:
                node.pop(field, None)
        self._dirty = True
        return node

    def delete(self, sid: str) -> None:
        self._nodes.pop(sid, None)
        self._dirty = True

    # ---------------------------------------------------------------- status/analytics
    def _ps(self, sid: str) -> dict:
        return self._analytics["per_statement"].setdefault(
            sid, {"status_history": [], "subagents": []}
        )

    def _record_status(self, sid: str, status: str) -> None:
        self._ps(sid)["status_history"].append({"status": status, "ts": _now()})
        self._dirty = True

    def set_status(self, sid: str, status: str) -> dict:
        if sid not in self._nodes:
            raise KeyError(f"unknown statement {sid!r}")
        if status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}"
            )
        self._record_status(sid, status)
        return self.update(sid, status=status)

    def completed_ids(self) -> list[str]:
        return [
            sid for sid, node in self._nodes.items()
            if not _is_meta(node) and node.get("status") in COMPLETED_STATES
        ]

    def record_metric(self, sid: str, role: str, data: dict) -> dict:
        entry = {"role": role, "ts": _now(), **(data or {})}
        self._ps(sid)["subagents"].append(entry)
        self._dirty = True
        return entry

    def analytics(self) -> dict:
        return self._analytics

    # ---------------------------------------------------------------- graph
    def _edge_dicts(self) -> list[dict]:
        return [
            {"id": sid, "dependencies": node.get("dependencies") or []}
            for sid, node in self._nodes.items() if not _is_meta(node)
        ]

    def topo_sorted(self) -> list[dict]:
        ordered, _ = topologically_sort_statements(self._edge_dicts())
        return [self._nodes[item["id"]] for item in ordered]

    def find_cycles(self) -> list[list[str]]:
        return find_dependency_cycles(self._edge_dicts())

    def forward_cone(self, ids: Iterable[str]) -> set[str]:
        return forward_dependency_cone(self._edge_dicts(), set(ids))

    def levels(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for node in self.topo_sorted():
            sid = node["statement_id"]
            deps = [
                dep for dep in (node.get("dependencies") or [])
                if dep in self._nodes and not _is_meta(self._nodes[dep])
            ]
            result[sid] = 0 if not deps else 1 + max((result.get(dep, 0) for dep in deps), default=0)
        return result

    def levels_grouped(self) -> dict[int, list[str]]:
        grouped: dict[int, list[str]] = {}
        for sid, level in self.levels().items():
            grouped.setdefault(level, []).append(sid)
        return {level: grouped[level] for level in sorted(grouped)}

    def recompute_dependents(self) -> None:
        reverse: dict[str, list[str]] = {sid: [] for sid in self._nodes}
        for sid, node in self._nodes.items():
            for dependency in node.get("dependencies") or []:
                if dependency in reverse:
                    reverse[dependency].append(sid)
        for sid, node in self._nodes.items():
            if _is_meta(node):
                continue
            dependents = sorted(reverse[sid])
            if (node.get("dependents") or []) != dependents:
                self.update(sid, dependents=dependents)

    # ---------------------------------------------------------------- compat helpers
    def upsert_summary(self, text: str, name: str = "Plan summary") -> dict:
        return self.add({
            "id": "Summary", "type": "Summary", "name": name,
            "content": text, "status": "n/a",
        })

    def load_do_not_import(self) -> list[dict]:
        return [
            {"import_path": import_path, "statement_id": sid}
            for sid, node in self._nodes.items()
            for import_path in (node.get("do_not_import") or [])
        ]

    def export(self) -> tuple[dict, dict]:
        output = []
        for node in self.topo_sorted():
            statement = {"id": node["statement_id"]}
            for key in _REQUIRED:
                statement[key] = node.get(key)
            for key in _OPTIONAL:
                value = node.get(key)
                if value not in (None, [], ""):
                    statement[key] = value
            output.append(statement)
        data: dict[str, Any] = {"statements": output}
        dni = self.load_do_not_import()
        if dni:
            data["do_not_import"] = dni
        return data, {"completed": sorted(self.completed_ids())}

    # ---------------------------------------------------------------- deterministic search
    def search(self, query: str, top_k: int = 5, rerank: bool = True,
               retrieve_k: int | None = None, kind: str = "all") -> dict[str, list[dict]]:
        """Return online-compatible groups ranked by deterministic lexical relevance.

        ``rerank`` and ``retrieve_k`` are accepted for command compatibility.  No online
        reranker is called; ties resolve by insertion order and then statement id.
        """
        del rerank, retrieve_k
        formal: list[tuple[float, int, dict]] = []
        informal: list[tuple[float, int, dict]] = []
        for node in self._nodes.values():
            score = _lexical_score(query, node)
            item = (score, int(node.get("order", 0)), node)
            (informal if _is_meta(node) else formal).append(item)

        def ranked(items: list[tuple[float, int, dict]], is_informal: bool) -> list[dict]:
            items.sort(key=lambda item: (-item[0], item[1], item[2]["statement_id"]))
            return [_hit(node, score, is_informal) for score, _, node in items[:top_k]]

        output: dict[str, list[dict]] = {"formal": [], "informal": []}
        if kind in {"all", "formal"}:
            output["formal"] = ranked(formal, False)
        if kind in {"all", "informal"}:
            output["informal"] = ranked(informal, True)
        return output


def import_statements_json(graph: OfflinePlanGraph, path) -> int:
    """Offline equivalent of :func:`compat.import_statements_json`."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    statements = raw.get("statements", raw) if isinstance(raw, dict) else raw
    progress_path = path.parent / "progress.json"
    completed: set[str] = set()
    if progress_path.exists():
        completed = set(json.loads(progress_path.read_text(encoding="utf-8")).get("completed", []))
    corrections_path = path.parent / "corrections.json"
    corrections = (
        json.loads(corrections_path.read_text(encoding="utf-8"))
        if corrections_path.exists() else {}
    )
    dni: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for entry in raw.get("do_not_import", []) or []:
            sid, import_path = entry.get("statement_id"), entry.get("import_path")
            if sid and import_path:
                dni.setdefault(sid, []).append(import_path)
    count = 0
    for statement in statements or []:
        node = dict(statement)
        sid = node["id"]
        node["status"] = "completed" if sid in completed else "pending"
        if sid in corrections:
            node["corrections"] = corrections[sid]
        if sid in dni:
            node["do_not_import"] = dni[sid]
        graph.add(node)
        count += 1
    return count
