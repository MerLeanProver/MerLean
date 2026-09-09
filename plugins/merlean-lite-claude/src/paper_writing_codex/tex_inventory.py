from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"\\(?P<level>section|subsection|subsubsection)\*?\s*\{(?P<title>[^{}]*)\}")
BASE_ENVIRONMENTS = (
    "theorem", "lemma", "proposition", "corollary", "definition", "conjecture",
    "claim", "assumption", "axiom", "remark", "example", "proof", "equation",
    "equation*", "align", "align*", "gather", "gather*", "multline", "multline*",
    "figure", "figure*", "table", "table*",
)
NEWTHEOREM_RE = re.compile(r"\\newtheorem\*?\s*\{([^{}]+)\}")
ANY_BEGIN_RE = re.compile(r"\\begin\{([^{}]+)\}")
STRUCTURAL_ENVIRONMENTS = {"itemize"}
LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|pageref|autoref|cref|Cref)\{([^{}]+)\}")
CITE_RE = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*)*\{([^{}]+)\}")
INCLUDE_RE = re.compile(
    r"\\(?P<command>input|include|subfile|bibliography|addbibresource)\s*\{(?P<target>[^{}]+)\}"
)
DISPLAY_RE = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
FOOTNOTE_RE = re.compile(r"\\footnote\{((?:[^{}]|\{[^{}]*\})*)\}", re.DOTALL)


def strip_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        cut = None
        for index, char in enumerate(line):
            if char == "%":
                backslashes = 0
                cursor = index - 1
                while cursor >= 0 and line[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2 == 0:
                    cut = index
                    break
        if cut is None:
            lines.append(line)
        else:
            ending = "\n" if line.endswith("\n") else ""
            comment_width = len(line) - cut - len(ending)
            lines.append(line[:cut] + (" " * comment_width) + ending)
    return "".join(lines)


def normalize_tex(text: str) -> str:
    return re.sub(r"\s+", " ", strip_comments(text)).strip()


def digest_text(text: str) -> str:
    return hashlib.sha256(normalize_tex(text).encode("utf-8")).hexdigest()


def _environment_re(names: set[str]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(name) for name in sorted(names, key=lambda value: (-len(value), value)))
    return re.compile(
        r"\\begin\{(?P<env>" + alternatives +
        r")\}(?P<title>\[[^\]]*\])?(?P<body>.*?)\\end\{(?P=env)\}",
        re.DOTALL,
    )


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def section_path(text: str, offset: int) -> list[str]:
    levels = {"section": 0, "subsection": 1, "subsubsection": 2}
    path: list[str] = []
    for match in SECTION_RE.finditer(text, 0, offset):
        level = levels[match.group("level")]
        path = path[:level]
        path.append(match.group("title"))
    return path


def _uid(kind: str, index: int, content: str, label: str | None = None) -> str:
    if label:
        return f"{kind}:{label}"
    return f"{kind}:{index}:{digest_text(content)[:12]}"


def _unit(kind: str, index: int, raw: str, source: str, offset: int,
          *, label: str | None = None, title: str = "", extra: dict[str, Any] | None = None,
          source_file: Path | None = None, forced_appendix: bool = False,
          verbatim_raw: str | None = None) -> dict[str, Any]:
    appendix_offset = source.find("\\appendix")
    # Hash the full prefix, not merely the preamble. A body-local \def or
    # \renewcommand can change a theorem's semantics without changing its visible text.
    # The conservative prefix hash deliberately requires semantic review whenever any
    # earlier context of a locked result changes.
    semantic_context = source[:offset]
    item: dict[str, Any] = {
        "id": _uid(kind, index, raw, label),
        "kind": kind,
        "label": label,
        "title": title,
        "line": line_number(source, offset),
        "normalized_sha256": digest_text(raw),
        "normalized_text": normalize_tex(raw),
        "raw_text": verbatim_raw if verbatim_raw is not None else raw,
        "raw_sha256": hashlib.sha256(
            (verbatim_raw if verbatim_raw is not None else raw).encode("utf-8")
        ).hexdigest(),
        "source_file": str(source_file) if source_file else None,
        "in_appendix": forced_appendix or (appendix_offset >= 0 and offset > appendix_offset),
        "section_path": section_path(source, offset),
        "semantic_context_sha256": digest_text(semantic_context),
    }
    if extra:
        item.update(extra)
    return item


def inventory_tex(
    path: Path,
    *,
    _seen: set[Path] | None = None,
    _forced_appendix: bool = False,
) -> dict[str, Any]:
    path = path.expanduser().absolute()
    real_path = path.resolve()
    seen = _seen if _seen is not None else set()
    if real_path in seen:
        return {
            "schema_version": 1, "source": str(path), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "units": [], "labels": [], "label_occurrences": [], "references": [], "citations": [],
            "includes": [], "source_files": [], "counts": {},
        }
    seen.add(real_path)
    original_bytes = path.read_bytes()
    source_digest = hashlib.sha256(original_bytes).hexdigest()
    original = original_bytes.decode("utf-8")
    text = strip_comments(original)
    units: list[dict[str, Any]] = []
    document_start = text.find("\\begin{document}")
    preamble = text[:document_start] if document_start >= 0 else ""
    preamble_sha256 = digest_text(preamble)
    if preamble:
        units.append(_unit(
            "preamble", 1, preamble, text, 0,
            source_file=path, forced_appendix=_forced_appendix,
            verbatim_raw=original[:document_start] if document_start >= 0 else original,
        ))

    for index, match in enumerate(SECTION_RE.finditer(text), 1):
        units.append(_unit(
            "section", index, match.group(0), text, match.start(),
            title=match.group("title"), extra={"level": match.group("level")},
            source_file=path, forced_appendix=_forced_appendix,
            verbatim_raw=original[match.start():match.end()],
        ))

    custom_theorems = set(NEWTHEOREM_RE.findall(preamble))
    recognized_environments = set(BASE_ENVIRONMENTS) | custom_theorems
    environment_re = _environment_re(recognized_environments)
    occupied: list[tuple[int, int]] = []
    for index, match in enumerate(environment_re.finditer(text), 1):
        raw = match.group(0)
        label_match = LABEL_RE.search(raw)
        title = (match.group("title") or "").strip("[]")
        env = match.group("env")
        kind = "statement" if env not in {
            "proof", "equation", "equation*", "align", "align*", "gather", "gather*",
            "multline", "multline*", "figure", "figure*", "table", "table*",
        } else env.rstrip("*")
        units.append(_unit(
            kind, index, raw, text, match.start(),
            label=label_match.group(1) if label_match else None,
            title=title,
            extra={"environment": env},
            source_file=path, forced_appendix=_forced_appendix,
            verbatim_raw=original[match.start():match.end()],
        ))
        occupied.append((match.start(), match.end()))

    # Inventory otherwise unknown environments as complete blocks. This catches
    # package-defined theorem/proof containers even when their declaration syntax is
    # unfamiliar. The document wrapper is excluded because every child is inventoried.
    unknown_environments = (
        set(ANY_BEGIN_RE.findall(text))
        - recognized_environments
        - {"document"}
    )
    for env in sorted(unknown_environments):
        generic_re = _environment_re({env})
        for index, match in enumerate(generic_re.finditer(text), 1):
            if env in STRUCTURAL_ENVIRONMENTS and any(
                start <= match.start() and match.end() <= end for start, end in occupied
            ):
                continue
            raw = match.group(0)
            label_match = LABEL_RE.search(raw)
            units.append(_unit(
                "environment", index, raw, text, match.start(),
                label=label_match.group(1) if label_match else None,
                title=(match.group("title") or "").strip("[]"),
                extra={"environment": env}, source_file=path, forced_appendix=_forced_appendix,
                verbatim_raw=original[match.start():match.end()],
            ))
            occupied.append((match.start(), match.end()))

    for index, match in enumerate(DISPLAY_RE.finditer(text), 1):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        raw = match.group(0)
        label_match = LABEL_RE.search(raw)
        units.append(_unit(
            "display", index, raw, text, match.start(),
            label=label_match.group(1) if label_match else None,
            source_file=path, forced_appendix=_forced_appendix,
            verbatim_raw=original[match.start():match.end()],
        ))
        occupied.append((match.start(), match.end()))

    for index, match in enumerate(FOOTNOTE_RE.finditer(text), 1):
        units.append(_unit(
            "footnote", index, match.group(0), text, match.start(),
            source_file=path, forced_appendix=_forced_appendix,
            verbatim_raw=original[match.start():match.end()],
        ))

    citations: list[str] = []
    for match in CITE_RE.finditer(text):
        citations.extend(key.strip() for key in match.group(1).split(",") if key.strip())
    for index, key in enumerate(dict.fromkeys(citations), 1):
        units.append({
            "id": f"citation:{key}", "kind": "citation", "label": key,
            "title": key, "line": None,
            "normalized_sha256": digest_text(key), "normalized_text": key,
            "source_file": str(path), "in_appendix": _forced_appendix,
        })

    include_matches = [
        (match.group("command"), match.group("target").strip(), match.start())
        for match in INCLUDE_RE.finditer(text)
    ]
    includes = [target for _, target, _ in include_matches]
    for index, target in enumerate(dict.fromkeys(includes), 1):
        units.append({
            "id": f"include:{index}:{digest_text(target)[:12]}", "kind": "include",
            "label": None, "title": target, "line": None,
            "normalized_sha256": digest_text(target), "normalized_text": target,
            "source_file": str(path), "in_appendix": _forced_appendix,
        })

    # Paragraph units catch substantive prose that labels alone miss. Exact unchanged
    # paragraphs pass automatically; rewritten or removed paragraphs need a ledger entry.
    body_offset = document_start + len("\\begin{document}") if document_start >= 0 else 0
    masked = list(text)
    mask_ranges = occupied + [(match.start(), match.end()) for match in SECTION_RE.finditer(text)]
    if document_start >= 0:
        mask_ranges.append((document_start, body_offset))
    document_end = text.find("\\end{document}")
    if document_end >= 0:
        mask_ranges.append((document_end, document_end + len("\\end{document}")))
    for start, end in mask_ranges:
        for cursor in range(start, min(end, len(masked))):
            if masked[cursor] != "\n":
                masked[cursor] = " "
    body_text = "".join(masked[body_offset:])
    structural_only = re.compile(
        r"(?:\\(?:section|subsection|subsubsection|chapter|part)\*?\s*\{[^{}]*\}\s*)+"
    )
    for index, match in enumerate(re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", body_text, re.DOTALL), 1):
        raw = match.group(0).strip()
        normalized = normalize_tex(raw)
        if len(normalized) < 8 or structural_only.fullmatch(normalized):
            continue
        if raw.count("\\begin{") or raw.count("\\end{"):
            continue
        units.append(_unit(
            "prose", index, raw, text, body_offset + match.start(),
            source_file=path, forced_appendix=_forced_appendix,
            verbatim_raw=original[
                body_offset + match.start():body_offset + match.end()
            ].strip(),
        ))

    label_occurrences = LABEL_RE.findall(text)
    labels = list(dict.fromkeys(label_occurrences))
    refs = list(dict.fromkeys(REF_RE.findall(text)))
    source_files: list[dict[str, Any]] = [{
        "path": str(path), "sha256": source_digest, "kind": "tex",
    }]
    appendix_offset = text.find("\\appendix")
    for command, target, offset in include_matches:
        raw_targets = [piece.strip() for piece in target.split(",") if piece.strip()]
        for raw_target in raw_targets:
            child = Path(raw_target)
            if not child.is_absolute():
                child = path.parent / child
            if command in {"input", "include", "subfile"} and not child.suffix:
                child = child.with_suffix(".tex")
            if command in {"bibliography", "addbibresource"} and not child.suffix:
                child = child.with_suffix(".bib")
            child = child.absolute()
            if not child.is_file():
                source_files.append({"path": str(child), "sha256": None, "kind": command, "missing": True})
                continue
            if command in {"input", "include", "subfile"}:
                child_inventory = inventory_tex(
                    child,
                    _seen=seen,
                    _forced_appendix=_forced_appendix or (appendix_offset >= 0 and offset > appendix_offset),
                )
                prefix = f"included:{child.name}:{digest_text(str(child.resolve()))[:8]}:"
                for child_unit in child_inventory["units"]:
                    copied = dict(child_unit)
                    copied["id"] = prefix + copied["id"]
                    units.append(copied)
                label_occurrences.extend(child_inventory.get("label_occurrences", []))
                refs.extend(value for value in child_inventory["references"] if value not in refs)
                citations.extend(value for value in child_inventory["citations"] if value not in citations)
                includes.extend(value for value in child_inventory["includes"] if value not in includes)
                source_files.extend(child_inventory.get("source_files", []))
            else:
                source_files.append({
                    "path": str(child), "sha256": hashlib.sha256(child.read_bytes()).hexdigest(), "kind": "bib",
                })

    labels = list(dict.fromkeys(label_occurrences))
    deduplicated_sources: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for source_entry in source_files:
        if source_entry["path"] not in seen_sources:
            seen_sources.add(source_entry["path"])
            deduplicated_sources.append(source_entry)
    tree_material = [
        {"path": entry["path"], "sha256": entry.get("sha256"), "kind": entry.get("kind")}
        for entry in deduplicated_sources
    ]
    return {
        "schema_version": 1,
        "source": str(path),
        "source_sha256": source_digest,
        "preamble_sha256": preamble_sha256,
        "units": units,
        "labels": labels,
        "label_occurrences": label_occurrences,
        "references": refs,
        "citations": list(dict.fromkeys(citations)),
        "includes": list(dict.fromkeys(includes)),
        "source_files": deduplicated_sources,
        "source_tree_sha256": hashlib.sha256(
            json.dumps(tree_material, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "counts": {
            "units": len(units),
            "sections": sum(u["kind"] == "section" for u in units),
            "statements": sum(u["kind"] == "statement" for u in units),
            "definitions": sum(u.get("environment") == "definition" for u in units),
            "citations": len(set(citations)),
        },
    }
