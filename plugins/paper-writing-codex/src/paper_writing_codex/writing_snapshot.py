"""Literal, read-only dependency discovery and sealed writing snapshots.

This is deliberately not a TeX interpreter. Dynamic file names fail closed;
installed packages are not copied and supplied code is never executed. Only
explicit local references are followed, never a directory or repository scan.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import unquote, urlsplit

from .tex_inventory import INCLUDE_RE, PACKAGE_RE, TEX_SOURCE_SUFFIXES, strip_comments
from .versioning import atomic_rename_noreplace

_ASSET_RE = re.compile(
    r"\\(?P<command>includegraphics\*?|includepdf|lstinputlisting|verbatiminput|VerbatimInput|pgfplotstableread)"
    r"\s*(?:\[[^\]]*\]\s*)?\{(?P<target>[^{}]+)\}"
)
_MINTED_RE = re.compile(r"\\inputminted\s*(?:\[[^\]]*\]\s*)?\{[^{}]+\}\s*\{([^{}]+)\}")
_IMPORT_RE = re.compile(r"\\(?:sub)?(?:import|inputfrom|includefrom)\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}")
_FILE_COMMAND_RE = re.compile(
    r"\\(?:inputminted|input|include|subfile|bibliography|addbibresource|"
    r"usepackage|RequirePackageWithOptions|RequirePackage|documentclass|LoadClassWithOptions|LoadClass|"
    r"includegraphics\*?|includepdf|lstinputlisting|verbatiminput|VerbatimInput|pgfplotstableread|"
    r"(?:sub)?(?:import|inputfrom|includefrom)|bibliographystyle|graphicspath)(?![A-Za-z])"
)
_GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".mps", ".ps")
_TEXT_SUFFIXES = TEX_SOURCE_SUFFIXES | {
    ".md", ".markdown", ".bib", ".bst", ".txt", ".csv", ".tsv", ".json",
    ".yaml", ".yml", ".lean", ".py", ".toml", ".xml", ".svg", ".tikz", ".pgf",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _safe_path(raw: Path) -> Path:
    """Reject symlinks/junctions before normalizing away any '..' segments."""
    raw = raw.expanduser().absolute()
    for item in [*reversed(raw.parents), raw]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"symlink or reparse-point path is not permitted: {item}")
    return Path(os.path.normpath(raw))


def _read(path: Path) -> bytes:
    path = _safe_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"dependency is not a regular file: {path}")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        data = handle.read()
        after = os.fstat(handle.fileno())
    final = _safe_path(path).stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, key) != getattr(info, key) for info in (opened, after, final) for key in fields):
        raise ValueError(f"source changed while snapshotting: {path}")
    return data


def _literal(target: str) -> Path:
    if not target.strip() or any(char in target for char in "\\{}#$\x00"):
        raise ValueError(f"dynamic or unsafe dependency path requires an explicit literal path: {target!r}")
    child = Path(target.strip())
    if child.is_absolute() or re.match(r"^[A-Za-z]:", target) or target.startswith("//"):
        raise ValueError(f"absolute dependency cannot be relocated safely; use a relative path: {target}")
    return child


def _resolve(target: str, path: Path, master: Path, *, suffix: str = "", optional: bool = False,
             search: tuple[Path, ...] = ()) -> list[Path]:
    child = _literal(target)
    graphics = suffix == "graphics"
    variants = [child] if child.suffix else [child.with_suffix(ext) for ext in _GRAPHICS_EXTENSIONS] if graphics else [child.with_suffix(suffix)] if suffix else [child]
    # Preserve every existing extension candidate: engine-specific graphics order
    # must not leave a potentially used local asset outside the digest.
    bases = tuple(dict.fromkeys((master, path.parent, *search)))
    candidates = list(dict.fromkeys(_safe_path(base / variant) for base in bases for variant in variants))
    found = [candidate for candidate in candidates if candidate.is_file()]
    if found:
        return found if graphics else found[:1]
    if optional and len(child.parts) == 1:
        return []  # Bare installed package/class/style, not a missing local file.
    raise ValueError(f"missing local dependency {target!r} referenced by {path}")


def _link_targets(text: str, *, tex: bool) -> list[str]:
    if tex:
        targets = re.findall(r"\\(?:href|url)\{([^{}]+)\}", text)
    else:
        # Examples in code fences are not assertions of local dependencies.
        text = re.sub(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", text)
        targets = re.findall(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", text)
        targets += re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", text)
    result = []
    for target in targets:
        target = target.strip("<>")
        parts = urlsplit(target)
        if target.startswith("#") or parts.netloc or (parts.scheme and not re.match(r"^[A-Za-z]:", target)):
            continue
        local = unquote(parts.path)
        if local:
            result.append(local)
    return result


def _collect(roots: list[Path]) -> tuple[dict[Path, bytes], list[tuple[Path, Path]]]:
    contents: dict[Path, bytes] = {}
    queue = [(root, root.parent) for root in roots]
    seen: set[tuple[Path, Path]] = set()
    edges: list[tuple[Path, Path]] = []
    graphics_paths: dict[Path, list[Path]] = {}
    pending_assets: list[tuple[Path, Path, str, str]] = []

    def append(parent: Path, child: Path, master: Path) -> None:
        edges.append((parent, child))
        queue.append((child, master))

    while queue:
        path, master = queue.pop(0)
        if (path, master) in seen:
            continue
        seen.add((path, master))
        if len(seen) > 10000:
            raise ValueError("dependency closure exceeds 10000 file/master contexts")
        contents.setdefault(path, _read(path))
        suffix = path.suffix.lower()
        if suffix not in TEX_SOURCE_SUFFIXES | {".md", ".markdown", ".tikz", ".pgf"}:
            continue
        text = contents[path].decode("utf-8-sig")
        is_tex = suffix not in {".md", ".markdown"}
        if is_tex:
            text = strip_comments(text)
            recognized = {
                match.start()
                for pattern in (INCLUDE_RE, PACKAGE_RE, _ASSET_RE, _MINTED_RE, _IMPORT_RE, _GRAPHICSPATH_RE,
                                re.compile(r"\\input\s+([^\s{}%]+)"),
                                re.compile(r"\\bibliographystyle\s*\{([^{}]+)\}"))
                for match in pattern.finditer(text)
            }
            for match in _FILE_COMMAND_RE.finditer(text):
                if match.start() not in recognized:
                    raise ValueError(f"nonliteral or unsupported dependency syntax {match.group(0)!r} in {path}")
            for match in _GRAPHICSPATH_RE.finditer(text):
                for directory in re.findall(r"\{([^{}]*)\}", match.group(1)):
                    relative = _literal(directory or ".")
                    graphics_paths.setdefault(master, []).extend((_safe_path(master / relative), _safe_path(path.parent / relative)))
            for match in sorted([*INCLUDE_RE.finditer(text), *PACKAGE_RE.finditer(text)], key=lambda item: item.start()):
                command = match.group("command")
                package = command in {"usepackage", "RequirePackage", "RequirePackageWithOptions"}
                cls = command in {"documentclass", "LoadClass", "LoadClassWithOptions"}
                extension = ".sty" if package else ".cls" if cls else ".bib" if command in {"bibliography", "addbibresource"} else ".tex"
                for target in match.group("target").split(","):
                    for child in _resolve(target, path, master, suffix=extension, optional=package or cls):
                        append(path, child, master)
            for target in re.findall(r"\\input\s+([^\s{}%]+)", text):
                for child in _resolve(target, path, master, suffix=".tex"):
                    append(path, child, master)
            for match in _IMPORT_RE.finditer(text):
                target = str(_literal(match.group(1)) / _literal(match.group(2))).replace("\\", "/")
                for child in _resolve(target, path, master, suffix=".tex"):
                    append(path, child, child.parent)
            for target in re.findall(r"\\bibliographystyle\s*\{([^{}]+)\}", text):
                for child in _resolve(target, path, master, suffix=".bst", optional=True):
                    append(path, child, master)
            for match in _ASSET_RE.finditer(text):
                extension = "graphics" if match.group("command").startswith("includegraphics") else ".pdf" if match.group("command") == "includepdf" else ""
                pending_assets.append((path, master, match.group("target"), extension))
            pending_assets.extend((path, master, target, "") for target in _MINTED_RE.findall(text))
        for target in _link_targets(text, tex=is_tex):
            for child in _resolve(target, path, master if is_tex else path.parent):
                append(path, child, child.parent if child.suffix.lower() in TEX_SOURCE_SUFFIXES else master)
    for path, master, target, extension in pending_assets:
        for child in _resolve(target, path, master, suffix=extension, search=tuple(graphics_paths.get(master, []))):
            edges.append((path, child))
            contents.setdefault(child, _read(child))
    return contents, edges


def _manifest_digest(manifest: dict[str, Any]) -> str:
    return _digest({
        "roots": [row["relative"] for row in manifest["roots"]],
        "files": sorted(({"relative": row["relative"], "sha256": row["sha256"], "size": row["size"]} for row in manifest["files"]), key=lambda row: row["relative"]),
        "edges": sorted(manifest.get("edges", []), key=lambda edge: (edge["from"], edge["to"])),
    })


def snapshot_sources(roots: list[Path], destination: Path) -> dict[str, Any]:
    """Publish a fresh immutable-by-receipt snapshot without overwriting anything.

    Common-parent layout preserves relative sibling includes. Absolute dependency
    references and nonliteral names require the author to make paths relocatable.
    The digest excludes original/destination locations, but includes dependency
    edges. No source file is changed and no supplied code is executed.
    """
    if not roots:
        raise ValueError("at least one source root is required")
    roots = list(dict.fromkeys(_safe_path(Path(root)) for root in roots))
    destination = _safe_path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    contents, edges = _collect(roots)
    try:
        common = Path(os.path.commonpath([str(path.parent) for path in contents]))
    except ValueError as exc:
        raise ValueError("source roots and dependencies must share a filesystem drive") from exc
    relative = {path: path.relative_to(common).as_posix() for path in contents}
    destination.parent.mkdir(parents=True, exist_ok=True)
    _safe_path(destination.parent)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.snapshot-", dir=destination.parent))
    manifest: dict[str, Any] = {
        "schema_version": 1, "destination": str(destination),
        "roots": [{"original": str(root), "snapshot": str(destination / "content" / relative[root]), "relative": relative[root]} for root in roots],
        "files": [], "edges": [{"from": relative[parent], "to": relative[child]} for parent, child in sorted(set(edges))],
    }
    try:
        for path in sorted(contents, key=lambda item: relative[item]):
            data = contents[path]
            target = staging / "content" / relative[path]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            manifest["files"].append({"original": str(path), "snapshot": str(destination / "content" / relative[path]), "relative": relative[path], "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "kind": path.suffix.lower().lstrip(".") or "asset"})
        for path, data in contents.items():
            if _read(path) != data:
                raise ValueError(f"source changed while snapshotting: {path}")
        manifest["digest"] = _manifest_digest(manifest)
        _safe_path(destination)
        if os.name == "nt":
            # Unlike POSIX rename, Windows rename refuses an existing target.
            os.rename(staging, destination)
        else:
            atomic_rename_noreplace(staging, destination)
    finally:
        # Only this privately created staging path is eligible for cleanup. Never
        # remove the destination: another actor may have won publication.
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def verify_snapshot(manifest: dict[str, Any], check_originals: bool = False) -> list[str]:
    """Read-only receipt validation, optionally checking live source drift."""
    errors: list[str] = []
    try:
        destination = _safe_path(Path(manifest["destination"]))
        if manifest.get("schema_version") != 1 or not manifest.get("roots") or not manifest.get("files"):
            raise ValueError("invalid snapshot schema or empty source set")
        if manifest.get("digest") != _manifest_digest(manifest):
            errors.append("snapshot manifest digest mismatch")
        relatives: set[str] = set()
        for row in manifest["files"]:
            rel = PurePosixPath(row["relative"])
            if rel.is_absolute() or ".." in rel.parts or "\\" in str(rel) or ":" in str(rel) or str(rel) in {"", "."}:
                raise ValueError("unsafe snapshot relative path")
            if str(rel) in relatives:
                raise ValueError("duplicate snapshot file path")
            relatives.add(str(rel))
            expected = destination / "content" / str(rel)
            if _safe_path(Path(row["snapshot"])) != expected:
                raise ValueError("snapshot file path is inconsistent with its receipt")
            for label, target in [("snapshot", expected)] + ([("original", Path(row["original"]))] if check_originals else []):
                try:
                    data = _read(target)
                    if hashlib.sha256(data).hexdigest() != row["sha256"] or len(data) != row["size"]:
                        errors.append(f"{label} content changed: {row['relative']}")
                    if label == "snapshot" and target.stat().st_nlink != 1:
                        errors.append(f"snapshot has an external hard link: {row['relative']}")
                except (OSError, ValueError) as exc:
                    errors.append(f"{label} verification failed: {exc}")
        for root in manifest["roots"]:
            if root["relative"] not in relatives or _safe_path(Path(root["snapshot"])) != destination / "content" / root["relative"]:
                raise ValueError("snapshot root is absent or has an inconsistent path")
            file_row = next(row for row in manifest["files"] if row["relative"] == root["relative"])
            if root["original"] != file_row["original"]:
                raise ValueError("snapshot root original path is inconsistent")
        for edge in manifest.get("edges", []):
            if edge["from"] not in relatives or edge["to"] not in relatives:
                raise ValueError("snapshot edge has an absent endpoint")
        if check_originals:
            # A new local package may shadow an installed one without modifying
            # any receipted file. Rediscover only the explicit root closure.
            live_contents, _ = _collect([_safe_path(Path(row["original"])) for row in manifest["roots"]])
            receipted_paths = {_safe_path(Path(row["original"])) for row in manifest["files"]}
            if set(live_contents) != receipted_paths:
                errors.append("original dependency closure changed")
        # Adding an unreceipted package can change TeX resolution just as changing
        # an existing one can. Reject extra files and symlink directories as well.
        content = destination / "content"
        for directory, dirs, files in os.walk(content, followlinks=False):
            for name in dirs + files:
                candidate = _safe_path(Path(directory) / name)
                if not candidate.is_dir() and candidate.relative_to(content).as_posix() not in relatives:
                    errors.append(f"unreceipted snapshot file: {candidate.relative_to(content).as_posix()}")
    except (KeyError, TypeError, OSError, ValueError, StopIteration) as exc:
        errors.append(f"invalid snapshot manifest: {exc}")
    return errors


def diff_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic path changes and UTF-8 text diffs; never emit binary."""
    errors = verify_snapshot(previous) + verify_snapshot(current)
    if errors:
        raise ValueError("cannot diff invalid snapshots: " + "; ".join(errors))
    old = {row["relative"]: row for row in previous["files"]}
    new = {row["relative"]: row for row in current["files"]}
    added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    modified = sorted(path for path in old.keys() & new.keys() if old[path]["sha256"] != new[path]["sha256"])
    changes, text_diffs = [], {}
    for status, paths in (("added", added), ("removed", removed), ("modified", modified)):
        for path in paths:
            changes.append({"path": path, "status": status, "before_sha256": old.get(path, {}).get("sha256"), "after_sha256": new.get(path, {}).get("sha256")})
            if Path(path).suffix.lower() not in _TEXT_SUFFIXES:
                continue
            try:
                before = Path(old[path]["snapshot"]).read_text(encoding="utf-8-sig") if path in old else ""
                after = Path(new[path]["snapshot"]).read_text(encoding="utf-8-sig") if path in new else ""
            except UnicodeDecodeError:
                continue
            if "\x00" not in before + after:
                text_diffs[path] = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=f"before/{path}", tofile=f"after/{path}"))
    return {"previous_digest": previous["digest"], "current_digest": current["digest"], "added": added, "removed": removed, "modified": modified, "changes": changes, "text_diffs": text_diffs}
