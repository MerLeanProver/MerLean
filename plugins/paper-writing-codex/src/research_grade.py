"""Fail-closed semantic grading shared by the repository and Codex release.

The auditor deliberately validates evidence files rather than accepting a collection of
self-attested booleans. It is still not a theorem prover: the evidence producer must run
Lean and an independent semantic review. Its job is to make omissions, stale evidence,
and the common "interface theorem reported as Gold" shape mechanically impossible.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
# These classes carry ordinary mathematical operations/laws and are safe to
# quantify as ambient structure.  Proposition-only classes (for example
# ``Fact`` or ``Subsingleton``) are intentionally absent: they belong in the
# public logical-premise census.  Expand this list only with an accompanying
# adversarial test and policy review.
STRUCTURAL_CLASS_ALLOWLIST = {
    "Inhabited", "Fintype", "DecidableEq", "AddCommGroup", "AddGroup", "AddCommMonoid", "AddMonoid",
    "CommGroup", "Group", "CommMonoid", "Monoid", "Module", "Algebra",
    "Field", "DivisionRing", "CommRing", "Ring", "CommSemiring", "Semiring",
    "LinearOrder", "PartialOrder", "TopologicalSpace", "MeasurableSpace",
    "NormedAddCommGroup", "InnerProductSpace",
}
TRUSTED_DATA_STRUCTURE_ALLOWLIST = STRUCTURAL_CLASS_ALLOWLIST | {
    "LinearMap", "AddMonoidHom", "Matrix",
    # Mathlib's bundled spaces and continuous maps are standard topological
    # data, not campaign-defined intended-model interfaces.
    "TopCat", "TopCat.Hom",
}
GRADES = {"BRONZE", "SILVER", "GOLD"}
BAD_RELATIONS = {"equivalent", "implies", "stronger", "carrier_collapse"}
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = {2}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _instance_premises(owner: dict[str, Any], public: set[str], errors: list[str]) -> dict[int, dict[str, Any]]:
    """Logical instance binders are public premises, never ambient structure."""
    entries = owner.get("instance_premises", [])
    result: dict[int, dict[str, Any]] = {}
    ids: set[str] = set()
    if not isinstance(entries, list):
        errors.append("INSTANCE_PREMISE_INVALID: instance_premises must be a list")
        return result
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("INSTANCE_PREMISE_INVALID: entry must be an object")
            continue
        index, ty, pid = (entry.get(k) for k in ("binder_index", "binder_type", "premise_id"))
        if (type(index) is not int or index < 0 or not _nonempty_string(ty)
                or not _nonempty_string(pid) or pid not in public
                or index in result or pid in ids):
            errors.append("INSTANCE_PREMISE_INVALID: unique index/type and enumerated public premise required")
            continue
        result[index] = entry
        ids.add(pid)
    return result


def _elaboration_context(owner: dict[str, Any], errors: list[str]) -> list[str]:
    """Only identifiers, never arbitrary Lean commands, enter the generated context."""
    if "elaboration_context" not in owner:
        return []
    context = owner["elaboration_context"]
    keys = {"universes", "open_namespaces", "open_scopes"}
    if not isinstance(context, dict) or set(context) - keys:
        errors.append("ELABORATION_CONTEXT_INVALID: expected narrow identifier arrays")
        return []
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if owner.get("elaboration_context_sha256") != digest:
        errors.append("ELABORATION_CONTEXT_INVALID: context hash mismatch")
    commands: list[str] = []
    for key, command in (("universes", "universe"), ("open_namespaces", "open"),
                         ("open_scopes", "open scoped")):
        values = context.get(key, [])
        pattern = r"[A-Za-z_][A-Za-z0-9_]*" if key == "universes" else r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
        if not isinstance(values, list) or any(not isinstance(v, str) or not re.fullmatch(pattern, v) for v in values):
            errors.append(f"ELABORATION_CONTEXT_INVALID: {key} must contain identifiers only")
            continue
        commands.extend(f"{command} {v}" for v in values)
    return commands


def _instance_type_census(owner: dict[str, Any], errors: list[str]) -> list[str] | None:
    values = owner.get("instance_binder_types")
    if values is None:
        return None
    signature = owner.get("signature", owner.get("target_signature", ""))
    if (not isinstance(signature, str) or not isinstance(values, list)
            or any(not _nonempty_string(v) for v in values)
            or len(values) != len(_top_level_square_binders(signature))):
        errors.append("INSTANCE_TYPE_CENSUS_INVALID: one canonical type per square binder required")
        return None
    return values


def _signature_binder_prefix(signature: str) -> str:
    """Exclude comments and result text from direct-premise exposure evidence."""
    signature = _strip_lean_comments(signature)
    depth = 0
    for index, char in enumerate(signature):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == ":" and depth == 0:
            return signature[:index]
    return signature


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _substantive_string(value: Any, minimum: int = 20) -> bool:
    """Reject checkbox-style evidence such as `yes`, `x`, or a bare label."""
    return isinstance(value, str) and len(value.strip()) >= minimum


def _identity_key(value: Any) -> str:
    """Canonicalize human/agent ids for independence comparisons."""
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def _installed_mathlib_identity(base_dir: Path | None) -> tuple[str, str] | None:
    if base_dir is None:
        return None
    campaign = base_dir.resolve()
    checkout = campaign / ".lake" / "packages" / "mathlib"
    manifest_path = campaign / "lake-manifest.json"
    try:
        manifest_payload = manifest_path.read_bytes()
        manifest = json.loads(manifest_payload)
    except (OSError, json.JSONDecodeError):
        return None
    package = next(
        (item for item in manifest.get("packages", []) if isinstance(item, dict) and item.get("name") == "mathlib"),
        None,
    )
    official_urls = {
        "https://github.com/leanprover-community/mathlib4",
    }
    if not isinstance(package, dict):
        return None
    manifest_url = str(package.get("url", "")).removesuffix(".git").rstrip("/")
    manifest_revision = package.get("rev")
    if manifest_url not in official_urls or not isinstance(manifest_revision, str):
        return None
    try:
        run = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        dirty = subprocess.run(
            ["git", "-C", str(checkout), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        origin = subprocess.run(
            ["git", "-C", str(checkout), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        tracked = subprocess.run(
            ["git", "-C", str(checkout), "ls-tree", "-r", "--name-only", "HEAD", "Mathlib"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        required = [
            subprocess.run(
                ["git", "-C", str(checkout), "cat-file", "-e", f"HEAD:{path}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            for path in ("Mathlib.lean", "lakefile.lean", "lean-toolchain")
        ]
    except (OSError, subprocess.TimeoutExpired):
        return None
    revision = run.stdout.strip()
    origin_url = origin.stdout.strip().removesuffix(".git").rstrip("/")
    return (revision, hashlib.sha256(manifest_payload).hexdigest()) if (
        run.returncode == 0
        and dirty.returncode == 0
        and not dirty.stdout.strip()
        and origin.returncode == 0
        and origin_url in official_urls
        and tracked.returncode == 0
        and len(tracked.stdout.splitlines()) >= 1000
        and all(item.returncode == 0 for item in required)
        and re.fullmatch(r"[0-9a-f]{40}", revision)
        and revision == manifest_revision
    ) else None


def _string_ids(value: Any, label: str, errors: list[str], *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty_string(item) for item in value):
        errors.append(f"SCHEMA_INVALID: {label} must be a list of non-empty strings")
        return []
    if nonempty and not value:
        errors.append(f"SCHEMA_INVALID: {label} must not be empty")
    if len(value) != len(set(value)):
        errors.append(f"SCHEMA_INVALID: {label} contains duplicate ids")
    return value


def _top_level_square_binders(signature: str) -> list[str]:
    """Return explicit ``[...]`` binders before the theorem's result colon.

    This deliberately records public typeclass context separately from logical
    proposition premises.  It is a small canonical-signature check, not a Lean
    parser: nested delimiters are handled, and only top-level square groups in
    the binder prefix are returned.
    """
    signature = _strip_lean_comments(signature)
    result: list[str] = []
    paren = brace = square = 0
    start: int | None = None
    for index, char in enumerate(signature):
        if char == ":" and paren == brace == square == 0:
            break
        if char == "(" and square == 0:
            paren += 1
        elif char == ")" and square == 0:
            paren = max(0, paren - 1)
        elif char == "{" and square == 0:
            brace += 1
        elif char == "}" and square == 0:
            brace = max(0, brace - 1)
        elif char == "[" and paren == brace == 0:
            if square == 0:
                start = index
            square += 1
        elif char == "]" and paren == brace == 0 and square:
            square -= 1
            if square == 0 and start is not None:
                result.append(signature[start:index + 1])
                start = None
    return result


def _top_level_named_binders(signature: str) -> tuple[list[str], list[str]]:
    """Return (explicit, implicit) named binders from a canonical theorem prefix."""
    signature = _strip_lean_comments(signature)
    groups: list[tuple[str, str]] = []
    paren = brace = square = 0
    start: int | None = None
    opener = ""
    for index, char in enumerate(signature):
        if char == ":" and paren == brace == square == 0:
            break
        if char == "(" and brace == square == 0:
            if paren == 0:
                start, opener = index + 1, "("
            paren += 1
        elif char == ")" and brace == square == 0 and paren:
            paren -= 1
            if paren == 0 and start is not None:
                groups.append((opener, signature[start:index]))
                start = None
        elif char == "{" and paren == square == 0:
            if brace == 0:
                start, opener = index + 1, "{"
            brace += 1
        elif char == "}" and paren == square == 0 and brace:
            brace -= 1
            if brace == 0 and start is not None:
                groups.append((opener, signature[start:index]))
                start = None
        elif char == "[" and paren == brace == 0:
            square += 1
        elif char == "]" and paren == brace == 0 and square:
            square -= 1

    explicit: list[str] = []
    implicit: list[str] = []
    for kind, content in groups:
        nested = 0
        colon = None
        for index, char in enumerate(content):
            if char in "({[":
                nested += 1
            elif char in ")}]":
                nested = max(0, nested - 1)
            elif char == ":" and nested == 0:
                colon = index
                break
        if colon is None:
            continue
        names = content[:colon].strip().split()
        if any(name == "_" for name in names):
            # Anonymous binders cannot be tied to a manifest premise/data id.
            names.append("<anonymous>")
        (explicit if kind == "(" else implicit).extend(name for name in names if name != "_")
    return explicit, implicit


def _evidence_path(
    reference: Any,
    base_dir: Path | None,
    label: str,
    errors: list[str],
) -> tuple[Path | None, bytes | None]:
    if not isinstance(reference, dict):
        errors.append(f"EVIDENCE_MISSING: {label} must be a path/sha256 object")
        return None, None
    relative = reference.get("path")
    digest = reference.get("sha256")
    if not _nonempty_string(relative) or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        errors.append(f"EVIDENCE_INVALID: {label} requires relative path and lowercase sha256")
        return None, None
    if base_dir is None:
        errors.append(f"EVIDENCE_BASE_MISSING: cannot resolve {label}")
        return None, None
    lexical = Path(relative)
    if lexical.is_absolute() or ".." in lexical.parts:
        errors.append(f"EVIDENCE_INVALID: {label} path must stay inside the manifest directory")
        return None, None
    root = base_dir.resolve()
    path = (root / lexical).resolve()
    if path != root and root not in path.parents:
        errors.append(f"EVIDENCE_INVALID: {label} escapes the manifest directory")
        return None, None
    try:
        payload = path.read_bytes()
    except OSError as exc:
        errors.append(f"EVIDENCE_MISSING: {label} cannot be read ({exc})")
        return path, None
    actual = hashlib.sha256(payload).hexdigest()
    if actual != digest:
        errors.append(f"EVIDENCE_STALE: {label} sha256 mismatch")
        return path, None
    return path, payload


def _json_evidence(
    reference: Any,
    base_dir: Path | None,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    _, payload = _evidence_path(reference, base_dir, label, errors)
    if payload is None:
        return None
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"EVIDENCE_INVALID: {label} is not valid JSON ({exc})")
        return None
    if not isinstance(value, dict):
        errors.append(f"EVIDENCE_INVALID: {label} must contain a JSON object")
        return None
    return value


def _evidence_snapshot(data: Any, base_dir: Path) -> tuple[list[dict[str, str]], str] | None:
    """Freeze every path/hash reference reachable through manifest-local JSON evidence."""
    root = base_dir.resolve()
    entries: dict[str, str] = {}
    visited: set[tuple[str, str]] = set()

    def walk(value: Any, context_dir: Path = root) -> bool:
        if isinstance(value, list):
            return all(walk(item, context_dir) for item in value)
        if not isinstance(value, dict):
            return True
        relative = value.get("path")
        digest = value.get("sha256")
        if isinstance(relative, str) and isinstance(digest, str) and _SHA256.fullmatch(digest):
            lexical = Path(relative)
            if lexical.is_absolute() or ".." in lexical.parts:
                return False
            candidates = [(root / lexical).resolve(), (context_dir / lexical).resolve()]
            matches: list[tuple[Path, bytes]] = []
            for candidate in dict.fromkeys(candidates):
                if candidate != root and root not in candidate.parents:
                    continue
                try:
                    candidate_payload = candidate.read_bytes()
                except OSError:
                    continue
                if hashlib.sha256(candidate_payload).hexdigest() == digest:
                    matches.append((candidate, candidate_payload))
            if not matches:
                return False
            for resolved, payload in matches:
                canonical = resolved.relative_to(root).as_posix()
                prior = entries.get(canonical)
                if prior is not None and prior != digest:
                    return False
                entries[canonical] = digest
                key = (canonical, digest)
                if key not in visited:
                    visited.add(key)
                    try:
                        nested = json.loads(payload)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        nested = None
                    if nested is not None and not walk(nested, resolved.parent):
                        return False
        return all(walk(item, context_dir) for item in value.values())

    if not walk(data):
        return None
    snapshot = [{"path": path, "sha256": entries[path]} for path in sorted(entries)]
    canonical_bytes = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()
    return snapshot, hashlib.sha256(canonical_bytes).hexdigest()


def _strip_lean_comments(text: str) -> str:
    """Strip nested Lean comments while preserving strings and line structure."""
    out: list[str] = []
    index = 0
    block_depth = 0
    in_string = False
    escaped = False
    while index < len(text):
        pair = text[index:index + 2]
        char = text[index]
        if block_depth:
            if pair == "/-":
                block_depth += 1
                out.extend("  ")
                index += 2
            elif pair == "-/":
                block_depth -= 1
                out.extend("  ")
                index += 2
            else:
                out.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if not in_string and pair == "/-":
            block_depth = 1
            out.extend("  ")
            index += 2
            continue
        if not in_string and pair == "--":
            while index < len(text) and text[index] != "\n":
                out.append(" ")
                index += 1
            continue
        out.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        index += 1
    return "".join(out)


def _decl_in_file(
    decl: Any,
    reference: Any,
    base_dir: Path | None,
    label: str,
    errors: list[str],
    expected_signature: str | None = None,
) -> None:
    _, payload = _evidence_path(reference, base_dir, label, errors)
    if payload is None or not _nonempty_string(decl):
        if not _nonempty_string(decl):
            errors.append(f"SCHEMA_INVALID: {label} requires a declaration name")
        return
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"EVIDENCE_INVALID: {label} is not UTF-8 Lean source")
        return
    without_comments = _strip_lean_comments(text)
    leaf = decl.rsplit(".", 1)[-1]
    declaration_pattern = rf"(?m)^\s*(?:theorem|lemma|def|abbrev|opaque)\s+{re.escape(leaf)}\b"
    if not re.search(declaration_pattern, without_comments):
        errors.append(f"DECLARATION_MISSING: {decl} not found in {label}")
    if expected_signature is not None:
        normalized_source = " ".join(without_comments.split())
        normalized_signature = " ".join(expected_signature.split())
        if normalized_signature not in normalized_source:
            errors.append(f"TARGET_MISMATCH: {decl} source does not contain the frozen signature")


def verify_kernel_runtime(data: dict[str, Any], base_dir: Path | None) -> list[str]:
    """Generate and run a typed schema-v2 Lean audit; never trust a submitted audit body."""
    errors: list[str] = []
    if data.get("grade") != "GOLD" or data.get("schema_version") != 2:
        return errors
    kernel = _json_evidence(data.get("kernel_evidence"), base_dir, "kernel_evidence", errors)
    contract = _json_evidence(data.get("target_contract"), base_dir, "target_contract", errors)
    if kernel is None or contract is None:
        return errors
    public_premises = set(contract.get("original_premise_ids", [])) | set(
        contract.get("condition_premise_ids", [])
    ) | set(contract.get("boundary_premise_ids", []))
    data_binders = set(contract.get("data_binder_ids", []))
    structural_binders = contract.get("structural_binders", [])
    verification = kernel.get("runtime_verification")
    if not isinstance(verification, dict):
        return [*errors, "KERNEL_RUNTIME_MISSING: schema-v2 Gold requires runtime_verification"]
    if verification.get("lib_dir") != ".":
        errors.append("KERNEL_RUNTIME_INVALID: lib_dir must be the manifest directory")
        return errors
    _, _ = _evidence_path(
        verification.get("audit_file"), base_dir, "kernel runtime audit_file", errors,
    )
    if base_dir is None:
        return errors
    expected_version = verification.get("lean_version")
    expected_transcript_hash = verification.get("transcript_sha256")
    if not _nonempty_string(expected_version):
        errors.append("KERNEL_RUNTIME_INVALID: lean_version is required")
    if not isinstance(expected_transcript_hash, str) or not _SHA256.fullmatch(expected_transcript_hash):
        errors.append("KERNEL_RUNTIME_INVALID: transcript_sha256 is required")
    roots = kernel.get("root_declarations", [])
    if not isinstance(roots, list) or not roots:
        return [*errors, "KERNEL_RUNTIME_INVALID: no roots to audit"]
    imports: list[str] = ["import Lean"]
    typed_checks: list[str] = []
    modules: list[str] = []
    for index, root in enumerate(roots):
        if not isinstance(root, dict):
            errors.append(f"KERNEL_RUNTIME_INVALID: root[{index}] must be an object")
            continue
        name = root.get("name")
        signature = root.get("signature")
        lean_ref = root.get("lean_file")
        lean_path, _ = _evidence_path(
            lean_ref, base_dir, f"kernel runtime root[{index}].lean_file", errors,
        )
        if not _nonempty_string(name) or not _nonempty_string(signature) or lean_path is None:
            continue
        try:
            relative = lean_path.relative_to(base_dir.resolve())
        except ValueError:
            errors.append(f"KERNEL_RUNTIME_INVALID: root[{index}] source escapes campaign")
            continue
        if relative.suffix != ".lean" or any(not part.replace("_", "").isalnum() for part in relative.with_suffix("").parts):
            errors.append(f"KERNEL_RUNTIME_INVALID: root[{index}] source is not an importable Lean module")
            continue
        module = ".".join(relative.with_suffix("").parts)
        modules.append(module)
        imports.append(f"import {module}")
        leaf = name.rsplit(".", 1)[-1]
        namespace = name.rsplit(".", 1)[0] if "." in name else ""
        example_signature = re.sub(
            rf"^\s*(?:theorem|lemma)\s+{re.escape(leaf)}\b", "example", signature,
            count=1,
        )
        if example_signature == signature:
            errors.append(f"KERNEL_RUNTIME_INVALID: cannot turn root[{index}] signature into a typed check")
            continue
        explicit_names, implicit_names = _top_level_named_binders(signature)
        if "<anonymous>" in explicit_names:
            errors.append(f"KERNEL_RUNTIME_INVALID: root[{index}] has an anonymous explicit binder")
            continue
        declared_binder_count = (
            len(explicit_names)
            + len(implicit_names)
            + len(_top_level_square_binders(signature))
        )
        application = " ".join([name, *explicit_names])
        typed_checks.extend([
            f"#check {name}",
            f"#print axioms {name}",
            f"run_cmd Lean.Elab.Command.liftTermElabM <| MerLean.auditBinders ``{name} {declared_binder_count}",
            *( [f"namespace {namespace}"] if namespace else [] ),
            "section",
            *_elaboration_context(root, errors),
            f"{example_signature} := by exact {application}",
            "end",
            *( [f"end {namespace}"] if namespace else [] ),
        ])
    if errors:
        return errors
    audit_support = r'''
namespace MerLean
open Lean Meta Elab Command

private def binderInfoName : BinderInfo → String
  | .default => "explicit"
  | .implicit => "implicit"
  | .strictImplicit => "strictImplicit"
  | .instImplicit => "instImplicit"

private def proofCarrier : Nat → Expr → MetaM Bool
  | 0, _ => return true -- fail closed if reducible carrier inspection exhausts its bound
  | fuel + 1, ty => do
      let sort ← whnf (← inferType ty)
      unless sort.isSort do return false -- class-operation arguments are not carriers
      if ← isProp ty then return true
      let reduced ← whnf ty
      if reduced.isAppOf ``Subtype then return true
      if reduced.isAppOf ``PLift || reduced.isAppOf ``ULift then
        return ← proofCarrier fuel reduced.getAppArgs.back!
      match reduced with
      | .forallE n domain body bi =>
          if ← isProp domain then return true
          withLocalDecl n bi domain fun x => proofCarrier fuel (body.instantiate1 x)
      | _ =>
          match reduced.getAppFn with
          | .fvar _ => return false -- a public type parameter or dependent family
          | .const n _ =>
              -- Deliberately narrow: arbitrary datatype/structure carriers can hide proofs.
              return !(#[``Nat, ``Int, ``Rat, ``Real, ``Complex, ``Bool, ``Unit, ``PUnit].contains n)
          | .sort _ => return false
          | _ => return true

private partial def instanceShape (ty : Expr) : MetaM (String × Array Bool × Bool × Array Bool) := do
  -- Inspect Pi syntax without unfolding DecidableEq into its implementation.
  match ty with
  | .forallE n domain body bi =>
      withLocalDecl n bi domain fun x => do
        let (head, domains, prop, args) ← instanceShape (body.instantiate1 x)
        return (head, #[← isProp domain] ++ domains, prop, args)
  | _ =>
      let head := match ty.getAppFn with
        | .const n _ => n.toString
        | _ => ""
      return (head, #[], ← isProp ty, ← ty.getAppArgs.mapM (proofCarrier 16))

def auditBinders (declName : Name) (declaredBinderCount : Nat) : Term.TermElabM Unit := do
  let info ← getConstInfo declName
  forallBoundedTelescope info.type declaredBinderCount fun xs resultType => do
    if declaredBinderCount = xs.size then
      for i in [:xs.size] do
        let fvar := xs[i]!
        let decl ← getFVarLocalDecl fvar
        let ty ← instantiateMVars decl.type
        let prop ← isProp ty
        let (terminalHead, piDomainProps, terminalIsProp, terminalPropArgs) ← instanceShape ty
        let tyText := toString (← ppExpr ty)
        let headTy ← whnf ty
        let env ← getEnv
        let structureName :=
          match headTy.getAppFn with
          | .const name _ =>
              if (Lean.getStructureInfo? env name).isSome then name.toString else ""
          | _ => ""
        let stableName :=
          if decl.userName.isAnonymous || decl.userName.hasMacroScopes then
            s!"_binder{i}"
          else decl.userName.eraseMacroScopes.toString
        logInfo (Json.mkObj [
          ("tag", Json.str "MERLEAN_BINDER"),
          ("declaration", Json.str declName.toString),
          ("index", toJson i),
          ("name", Json.str stableName),
          ("binderInfo", Json.str (binderInfoName decl.binderInfo)),
          ("type", Json.str tyText),
          ("structure", Json.str structureName),
          ("terminalHead", Json.str terminalHead),
          ("piDomainProps", toJson piDomainProps),
          ("terminalIsProp", toJson terminalIsProp),
          ("terminalPropArgs", toJson terminalPropArgs),
          ("isProp", toJson prop)
        ]).compress
      let resultIsNegation := resultType.isAppOf ``Not
      let reducedResultType ← whnf resultType
      logInfo (Json.mkObj [
        ("tag", Json.str "MERLEAN_RESULT"),
        ("declaration", Json.str declName.toString),
        ("type", Json.str (toString (← ppExpr resultType))),
        ("isProp", toJson (← isProp resultType)),
        ("isNegation", toJson resultIsNegation),
        ("hasLeadingForall", toJson reducedResultType.isForall)
      ]).compress
    else
      throwError "frozen signature declares {declaredBinderCount} binders, but Lean exposed only {xs.size} before the result"
end MerLean
'''
    generated = "\n".join(dict.fromkeys(imports)) + "\n\n" + audit_support + "\n" + "\n".join(typed_checks) + "\n"
    audit_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", prefix="MerLeanGeneratedAudit_",
            dir=base_dir, delete=False, encoding="utf-8",
        ) as handle:
            handle.write(generated)
            audit_path = Path(handle.name)
        version_run = subprocess.run(
            ["lake", "env", "lean", "--version"], cwd=base_dir,
            capture_output=True, text=True, timeout=30, check=False,
        )
        build_run = subprocess.run(
            ["lake", "build", *dict.fromkeys(modules)], cwd=base_dir,
            capture_output=True, text=True, timeout=300, check=False,
        )
        run = subprocess.run(
            ["lake", "env", "lean", str(audit_path)], cwd=base_dir,
            capture_output=True, text=True, timeout=300, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"KERNEL_RUNTIME_FAILED: {exc}")
        return errors
    finally:
        if audit_path is not None:
            try:
                audit_path.unlink()
            except OSError:
                pass
    actual_version = (version_run.stdout + version_run.stderr).strip()
    if version_run.returncode != 0 or actual_version != expected_version:
        errors.append("KERNEL_RUNTIME_STALE: Lean version differs from the recorded run")
    if build_run.returncode != 0:
        errors.append("KERNEL_RUNTIME_FAILED: exact root module did not build")
    transcript = run.stdout + run.stderr
    if run.returncode != 0:
        errors.append("KERNEL_RUNTIME_FAILED: Lean audit module did not compile")
    if hashlib.sha256(transcript.encode()).hexdigest() != expected_transcript_hash:
        errors.append("KERNEL_RUNTIME_STALE: Lean audit transcript hash differs")
    for root in roots if isinstance(roots, list) else []:
        name = root.get("name") if isinstance(root, dict) else None
        if _nonempty_string(name) and name not in transcript:
            errors.append(f"KERNEL_RUNTIME_INVALID: transcript does not audit root {name}")
    if "sorryAx" in transcript or "declaration uses 'sorry'" in transcript:
        errors.append("KERNEL_RUNTIME_HOLE: Lean audit reports sorry")
    binder_records: dict[str, list[dict[str, Any]]] = {}
    result_records: dict[str, list[dict[str, Any]]] = {}
    for line in transcript.splitlines():
        if "MERLEAN_BINDER" not in line and "MERLEAN_RESULT" not in line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            errors.append("KERNEL_RUNTIME_BINDER_CENSUS: malformed generated binder record")
            continue
        declaration = record.get("declaration")
        if record.get("tag") == "MERLEAN_BINDER":
            binder_records.setdefault(declaration, []).append(record)
        elif record.get("tag") == "MERLEAN_RESULT":
            result_records.setdefault(declaration, []).append(record)
    for root in roots:
        if not isinstance(root, dict):
            continue
        name = root.get("name")
        records = binder_records.get(name, [])
        if [record.get("index") for record in records] != list(range(len(records))):
            errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} binder indices are missing, duplicated, or reordered")
        results = result_records.get(name, [])
        if len(results) != 1:
            errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} needs exactly one result record")
        else:
            result = results[0]
            if result.get("isProp") is not True:
                errors.append(f"KERNEL_RUNTIME_RESULT_INVALID: {name} result is not a proposition")
            if not isinstance(result.get("isNegation"), bool) or not isinstance(
                result.get("hasLeadingForall"), bool
            ):
                errors.append(
                    f"KERNEL_RUNTIME_RESULT_INVALID: {name} result-shape record is incomplete"
                )
            elif result.get("hasLeadingForall") is True and result.get("isNegation") is not True:
                errors.append(
                    f"KERNEL_RUNTIME_HIDDEN_RESULT_PREMISE: {name} has a leading implication/forall after the result colon; expose it as a named public binder"
                )
        seen_public: set[str] = set()
        seen_data: set[str] = set()
        seen_structural: list[str] = []
        instance_map = _instance_premises(root, set(root.get("premise_ids", [])), errors)
        used_instance_map: set[int] = set()
        mapped_ids = {entry["premise_id"] for entry in instance_map.values()}
        ordinary_names = [record.get("name") for record in records
                          if record.get("binderInfo") != "instImplicit"]
        if len(ordinary_names) != len(set(ordinary_names)):
            errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} ordinary binder names are duplicated")
        if any(record.get("binderInfo") != "instImplicit" and record.get("name") in mapped_ids
               for record in records):
            errors.append(f"INSTANCE_PREMISE_INVALID: {name} instance ids alias ordinary binders")
        canonical_types = _instance_type_census(root, errors)
        for record in records:
            binder_name = record.get("name")
            binder_type = record.get("type")
            binder_info = record.get("binderInfo")
            is_prop = record.get("isProp")
            structure = record.get("structure")
            # Proposition binders are already governed by the public-premise
            # census. Requiring an intended-data-model adapter for a named
            # condition would duplicate that gate and, for structures such as
            # `And`, falsely suggest that the condition had been discharged.
            if is_prop is False and _nonempty_string(structure):
                audited_types = {
                    item.get("lean_type")
                    for item in data.get("interfaces", []) if isinstance(item, dict)
                }
                if (
                    structure not in TRUSTED_DATA_STRUCTURE_ALLOWLIST
                    and structure not in audited_types
                ):
                    errors.append(
                        f"KERNEL_RUNTIME_STRUCTURE_UNAUDITED: {name} binder {binder_name} uses custom structure {structure} without an intended-model interface"
                    )
            if binder_info == "instImplicit":
                seen_structural.append(f"[{binder_type}]")
                mapped = instance_map.get(record.get("index"))
                if is_prop is True and mapped is not None and mapped["binder_type"] == binder_type:
                    seen_public.add(mapped["premise_id"])
                    used_instance_map.add(record["index"])
                elif is_prop is not False:
                    errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: proposition-valued instance {binder_type} must be a public premise/interface")
                else:
                    head = record.get("terminalHead")
                    domains = record.get("piDomainProps")
                    terminal_prop = record.get("terminalIsProp")
                    prop_args = record.get("terminalPropArgs")
                    # Older simple census fixtures can use the exact resolved structure;
                    # Pi families and reducible DecidableEq require the new Lean record.
                    if head is None and structure in STRUCTURAL_CLASS_ALLOWLIST:
                        head, domains, terminal_prop, prop_args = structure, [], False, []
                    if (head not in STRUCTURAL_CLASS_ALLOWLIST or terminal_prop is not False
                            or not isinstance(domains, list)
                            or any(type(p) is not bool or p for p in domains)
                            or not isinstance(prop_args, list)
                            or any(type(p) is not bool for p in prop_args)
                            or (any(prop_args) and head not in {"Fintype", "DecidableEq"})):
                        errors.append(f"KERNEL_RUNTIME_STRUCTURE_UNAUDITED: instance {binder_type} is not an approved structural family")
            elif is_prop is True:
                seen_public.add(binder_name)
            elif is_prop is False:
                seen_data.add(binder_name)
            else:
                errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} has an invalid binder record")
        if used_instance_map != set(instance_map):
            errors.append(f"INSTANCE_PREMISE_INVALID: {name} mapping does not match actual Prop instance binders")
        expected_public = set(root.get("premise_ids", []))
        if root.get("signature_hash") == kernel.get("target_signature_hash"):
            expected_data = data_binders
            expected_structural = structural_binders
        else:
            expected_data = set(root.get("data_binder_ids", []))
            expected_structural = root.get("structural_binders", [])
            if not isinstance(expected_structural, list):
                errors.append(
                    f"KERNEL_RUNTIME_BINDER_CENSUS: {name} structural_binders must be a list"
                )
                expected_structural = []
        if seen_public != expected_public:
            errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} proposition binders do not equal the public premise census")
        if seen_data != expected_data:
            errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} data binders do not equal data_binder_ids")
        if canonical_types is not None:
            expected_structural = [f"[{ty}]" for ty in canonical_types]
        if seen_structural != expected_structural:
            errors.append(f"KERNEL_RUNTIME_BINDER_CENSUS: {name} instance binders do not equal structural_binders")
    axiom_chunks = re.findall(r"depends on axioms:\s*\[([^\]]*)\]", transcript)
    allowed_leafs = {item.rsplit(".", 1)[-1] for item in STANDARD_AXIOMS}
    transcript_axioms: set[str] = set()
    for chunk in axiom_chunks:
        names = {item.strip().strip("'\"") for item in chunk.split(",") if item.strip()}
        transcript_axioms.update(names)
        if names - STANDARD_AXIOMS and {name.rsplit(".", 1)[-1] for name in names} - allowed_leafs:
            errors.append("KERNEL_RUNTIME_AXIOMS_OPEN: transcript contains a non-standard axiom")
    expected_axioms = {
        axiom
        for root in roots if isinstance(root, dict)
        for axiom in root.get("axioms", []) if isinstance(axiom, str)
    }
    if transcript_axioms != expected_axioms:
        errors.append("KERNEL_RUNTIME_AXIOMS_MISMATCH: transcript and root evidence differ")
    return errors


def _exact_checklist(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {label} must not be empty")
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {label}[{index}] must be an object")
            continue
        if not _nonempty_string(item.get("source")) or not _nonempty_string(item.get("lean")):
            errors.append(
                f"BOUNDARY_AUDIT_INCOMPLETE: {label}[{index}] needs source and Lean clauses"
            )
        if item.get("status") != "exact":
            errors.append(f"BOUNDARY_NOT_EXACT: {label}[{index}] is not marked exact")


def _path_is_manifest_ref(path: Path | None, base_dir: Path | None) -> bool:
    if path is None or base_dir is None:
        return False
    try:
        parts = path.relative_to(base_dir.resolve()).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] in {"ref", "refs"}


def _audit_boundary_source_closure(
    assumption: dict[str, Any],
    all_assumptions: list[Any],
    base_dir: Path | None,
    manifest_author: Any,
    gold_auditor: Any,
    errors: list[str],
) -> None:
    """Require a manifest-local, hash-closed graph behind every cited boundary."""
    name = assumption.get("name", "<unnamed>")
    closure_ref = assumption.get("source_closure")
    closure = _json_evidence(
        closure_ref, base_dir,
        f"boundary {name}.source_closure", errors,
    )
    if closure is None:
        return
    closure_relative = closure_ref.get("path") if isinstance(closure_ref, dict) else None
    closure_path = (
        (base_dir.resolve() / Path(closure_relative)).resolve()
        if base_dir is not None and isinstance(closure_relative, str)
        else None
    )
    if not _path_is_manifest_ref(closure_path, base_dir):
        errors.append(f"SOURCE_OUTSIDE_REF: {name} source closure must be under ref/ or refs/")
    if closure.get("schema_version") != 1 or closure.get("status") != "self_contained":
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} closure is not self-contained schema v1")
        return

    primary_items = closure.get("primary_sources")
    leaf_items = closure.get("leaves")
    face_items = closure.get("faces")
    if not isinstance(primary_items, list) or not primary_items:
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} has no primary-source registry")
        return
    if not isinstance(leaf_items, list) or not leaf_items:
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} has no leaf-source registry")
        return
    if not isinstance(face_items, list) or not face_items:
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} has no joint-face registry")
        return

    def indexed(items: list[Any], label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(items):
            item_id = item.get("id") if isinstance(item, dict) else None
            if not _nonempty_string(item_id) or item_id in result:
                errors.append(
                    f"BOUNDARY_SOURCE_CLOSURE: {name} {label}[{index}] has a missing/duplicate id"
                )
            else:
                result[item_id] = item
        return result

    primaries = indexed(primary_items, "primary_sources")
    leaves = indexed(leaf_items, "leaves")
    faces = indexed(face_items, "faces")

    def closure_key(item: Any) -> tuple[Any, Any] | None:
        if not isinstance(item, dict):
            return None
        reference = item.get("source_closure")
        if not isinstance(reference, dict):
            return None
        return reference.get("path"), reference.get("sha256")

    current_closure_key = closure_key(assumption)
    closure_assumptions = {
        item.get("id"): item
        for item in all_assumptions
        if isinstance(item, dict)
        and item.get("kind") == "boundary"
        and _nonempty_string(item.get("id"))
        and closure_key(item) == current_closure_key
    }
    if set(faces) != set(closure_assumptions):
        errors.append(
            f"BOUNDARY_SOURCE_CLOSURE: {name} face registry is not exactly the manifest assumptions bound to this closure"
        )

    forbidden_auditors = {
        key for key in (_identity_key(manifest_author), _identity_key(gold_auditor)) if key
    }
    for item in all_assumptions:
        if not isinstance(item, dict):
            continue
        audits = item.get("independent_source_audits")
        if not isinstance(audits, list):
            continue
        for source_audit in audits:
            if isinstance(source_audit, dict):
                key = _identity_key(source_audit.get("auditor"))
                if key:
                    forbidden_auditors.add(key)
    leaf_boundary_ids: dict[str, set[str]] = {}
    used_primaries: set[str] = set()
    for leaf_id, leaf in leaves.items():
        packet_path, _ = _evidence_path(
            leaf.get("packet"), base_dir,
            f"boundary {name}.source_closure.leaf[{leaf_id}].packet", errors,
        )
        if packet_path is not None and not _path_is_manifest_ref(packet_path, base_dir):
            errors.append(f"SOURCE_OUTSIDE_REF: {name} leaf {leaf_id} is outside ref/ or refs/")
        leaf_boundary_ids[leaf_id] = set(_string_ids(
            leaf.get("boundary_ids"),
            f"boundary {name}.source_closure.leaf[{leaf_id}].boundary_ids",
            errors, nonempty=True,
        ))
        primary_ids = _string_ids(
            leaf.get("primary_ids"),
            f"boundary {name}.source_closure.leaf[{leaf_id}].primary_ids",
            errors, nonempty=True,
        )
        used_primaries.update(primary_ids)
        _exact_checklist(
            leaf.get("hypothesis_checklist"),
            f"{name}.source_closure.leaf[{leaf_id}].hypothesis_checklist", errors,
        )
        _exact_checklist(
            leaf.get("conclusion_checklist"),
            f"{name}.source_closure.leaf[{leaf_id}].conclusion_checklist", errors,
        )

    if used_primaries != set(primaries):
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} primary registry is not exactly reachable from leaves")
    for primary_id, primary in primaries.items():
        primary_path, payload = _evidence_path(
            primary.get("evidence"), base_dir,
            f"boundary {name}.source_closure.primary[{primary_id}].evidence", errors,
        )
        if primary_path is not None and not _path_is_manifest_ref(primary_path, base_dir):
            errors.append(f"SOURCE_OUTSIDE_REF: {name} primary {primary_id} is outside ref/ or refs/")
        if primary.get("exact_excerpt") is not True:
            errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} primary {primary_id} is not exact")
        original_hash = primary.get("original_full_sha256")
        if not isinstance(original_hash, str) or not _SHA256.fullmatch(original_hash):
            errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} primary {primary_id} lacks original hash")
        locators = primary.get("locators")
        if not isinstance(locators, list) or not locators or any(
            not _nonempty_string(locator) for locator in locators
        ):
            errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} primary {primary_id} lacks locators")
        elif payload is not None:
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} primary {primary_id} is not UTF-8")
            else:
                for locator in locators:
                    if locator not in text:
                        errors.append(
                            f"BOUNDARY_SOURCE_CLOSURE: {name} primary {primary_id} locator is absent: {locator}"
                        )

    all_face_leaves: set[str] = set()
    used_joint_report_refs: set[tuple[Any, Any]] = set()
    for face_id, candidate in faces.items():
        candidate_leaf_ids = _string_ids(
            candidate.get("leaf_ids"),
            f"boundary {name}.source_closure.face[{face_id}].leaf_ids",
            errors, nonempty=True,
        )
        candidate_leaf_set = set(candidate_leaf_ids)
        all_face_leaves.update(candidate_leaf_set)
        unknown_leaves = candidate_leaf_set - set(leaves)
        if unknown_leaves:
            errors.append(
                f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} references unknown leaves"
            )
        expected_boundary_ids = set().union(*(
            leaf_boundary_ids.get(leaf_id, set()) for leaf_id in candidate_leaf_ids
        )) if candidate_leaf_ids else set()
        candidate_boundary_ids = set(_string_ids(
            candidate.get("boundary_ids"),
            f"boundary {name}.source_closure.face[{face_id}].boundary_ids",
            errors, nonempty=True,
        ))
        if candidate_boundary_ids != expected_boundary_ids:
            errors.append(
                f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} boundary ids do not equal its leaf boundary census"
            )
        bound_assumption = closure_assumptions.get(face_id)
        bound_source_ref = (
            bound_assumption.get("source_evidence")
            if isinstance(bound_assumption, dict) else None
        )
        bound_source_hash = (
            bound_source_ref.get("sha256") if isinstance(bound_source_ref, dict) else None
        )
        if bound_source_hash != candidate.get("joint_source_sha256"):
            errors.append(
                f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} joint source hash is not bound to its manifest assumption"
            )

        independent = set(_string_ids(
            candidate.get("independent_leaf_ids"),
            f"boundary {name}.source_closure.face[{face_id}].independent_leaf_ids",
            errors,
        ))
        if not independent.issubset(candidate_leaf_set):
            errors.append(
                f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} has an unknown independent leaf"
            )
        edges = candidate.get("compatibility_edges")
        if not isinstance(edges, list) or (len(candidate_leaf_ids) > 1 and not edges):
            errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} compatibility edges are incomplete")
            edges = []
        edge_ids: set[str] = set()
        covered_leaves: set[str] = set(independent)
        for edge_index, edge in enumerate(edges):
            label = f"boundary {name}.source_closure.face[{face_id}].edge[{edge_index}]"
            if not isinstance(edge, dict):
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {label} must be an object")
                continue
            edge_id = edge.get("id")
            if not _nonempty_string(edge_id) or edge_id in edge_ids:
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {label} has a missing/duplicate id")
            else:
                edge_ids.add(edge_id)
            endpoints = set(_string_ids(
                edge.get("leaf_ids"), f"{label}.leaf_ids", errors, nonempty=True,
            ))
            if len(endpoints) < 2 or not endpoints.issubset(candidate_leaf_set):
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {label} needs at least two valid endpoints")
            covered_leaves.update(endpoints)
            if not _substantive_string(edge.get("shared_datum")):
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {label} lacks a shared datum")
        if covered_leaves != candidate_leaf_set:
            errors.append(
                f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} has uncovered compatibility leaves"
            )

        canonical_edges = sorted(({
            "id": edge.get("id"),
            "leaf_ids": sorted(set(edge.get("leaf_ids", []))),
            "shared_datum": edge.get("shared_datum"),
        } for edge in edges if isinstance(edge, dict)), key=lambda edge: str(edge.get("id")))
        face_audits = candidate.get("joint_face_audits")
        if not isinstance(face_audits, list) or len(face_audits) < 2:
            errors.append(
                f"BOUNDARY_SOURCE_CLOSURE: {name} face {face_id} needs two complete joint-face audits"
            )
            face_audits = []
        face_auditors: set[str] = set()
        for audit_index, audit in enumerate(face_audits):
            audit_label = (
                f"boundary {name}.source_closure.face[{face_id}].joint_face_audits[{audit_index}]"
            )
            auditor = audit.get("auditor") if isinstance(audit, dict) else None
            auditor_key = _identity_key(auditor)
            if (
                not auditor_key
                or auditor_key in face_auditors
                or auditor_key in forbidden_auditors
            ):
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {audit_label} has a non-independent auditor")
            else:
                face_auditors.add(auditor_key)
            report_ref = audit.get("report") if isinstance(audit, dict) else None
            report_key = (
                report_ref.get("path"), report_ref.get("sha256")
            ) if isinstance(report_ref, dict) else (None, None)
            if report_key in used_joint_report_refs:
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {audit_label} reuses a joint-face report")
            else:
                used_joint_report_refs.add(report_key)
            report_path, _ = _evidence_path(report_ref, base_dir, audit_label, errors)
            if report_path is not None and not _path_is_manifest_ref(report_path, base_dir):
                errors.append(f"SOURCE_OUTSIDE_REF: {audit_label} is outside ref/ or refs/")
            report = _json_evidence(report_ref, base_dir, audit_label, errors)
            findings = report.get("findings") if isinstance(report, dict) else None
            report_boundary_ids = (
                sorted(report.get("boundary_ids", [])) if isinstance(report, dict)
                and isinstance(report.get("boundary_ids"), list) else None
            )
            report_edges = (
                sorted(report.get("edges", []), key=lambda edge: str(edge.get("id")))
                if isinstance(report, dict)
                and isinstance(report.get("edges"), list)
                and all(isinstance(edge, dict) for edge in report.get("edges", []))
                else None
            )
            if report_edges is not None:
                report_edges = [{
                    "id": edge.get("id"),
                    "leaf_ids": sorted(edge.get("leaf_ids", []))
                    if isinstance(edge.get("leaf_ids"), list) else None,
                    "shared_datum": edge.get("shared_datum"),
                } for edge in report_edges]
            if (
                report is None
                or report.get("verdict") != "passed"
                or report.get("auditor") != auditor
                or report.get("boundary_id") != face_id
                or report.get("source_sha256") != candidate.get("joint_source_sha256")
                or report_boundary_ids != sorted(candidate_boundary_ids)
                or report_edges != canonical_edges
                or not isinstance(findings, dict)
                or not _substantive_string(findings.get("notation"))
                or not _substantive_string(findings.get("hypotheses"))
            ):
                errors.append(f"BOUNDARY_SOURCE_CLOSURE: {audit_label} report is incomplete or does not bind the complete face")

    if all_face_leaves != set(leaves):
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} leaf registry is not exactly reachable from faces")
    face = faces.get(assumption.get("id"))
    if face is None:
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} has no face for its assumption id")
        return
    source_ref = assumption.get("source_evidence")
    source_hash = source_ref.get("sha256") if isinstance(source_ref, dict) else None
    if face.get("joint_source_sha256") != source_hash:
        errors.append(f"BOUNDARY_SOURCE_CLOSURE: {name} joint source hash is not bound")


def _audit_boundary_assumption(
    assumption: dict[str, Any],
    all_assumptions: list[Any],
    base_dir: Path | None,
    manifest_author: Any,
    gold_auditor: Any,
    errors: list[str],
) -> None:
    name = assumption.get("name", "<unnamed>")
    if assumption.get("status") != "source-verified":
        errors.append(f"UNRESOLVED_PREMISE: {name} (boundary/source audit open)")
    if assumption.get("exposure") != "direct_binder":
        errors.append(f"HIDDEN_CONDITION: boundary premise {name} is not a direct theorem binder")
    if not _nonempty_string(assumption.get("lean_binder")):
        errors.append(f"HIDDEN_CONDITION: boundary premise {name} lacks exact lean_binder text")
    if assumption.get("correspondence") != "exact":
        errors.append(f"BOUNDARY_NOT_EXACT: {name} is not a 100% source correspondence")

    _audit_boundary_source_closure(
        assumption, all_assumptions, base_dir, manifest_author, gold_auditor, errors,
    )

    cost = assumption.get("formalization_cost")
    if not isinstance(cost, dict):
        errors.append(f"BOUNDARY_COST_GATE: {name} lacks a structured formalization-cost decision")
    else:
        cost_record = _json_evidence(
            cost.get("record"), base_dir, f"boundary {name}.formalization_cost.record", errors,
        )
        if cost_record is not None:
            if cost_record.get("boundary_id") != assumption.get("id"):
                errors.append(f"BOUNDARY_COST_GATE: {name} cost record has the wrong boundary id")
            if cost_record.get("source_sha256") != assumption.get("source_evidence", {}).get("sha256"):
                errors.append(f"BOUNDARY_COST_GATE: {name} cost record has the wrong source hash")
            if cost_record.get("standard_result") is not True:
                errors.append(f"BOUNDARY_COST_GATE: {name} is not certified as a standard/well-known result")
            if cost_record.get("mathlib_status") != "not_available":
                errors.append(f"BOUNDARY_COST_GATE: {name} is not certified absent from Mathlib")
            revision = cost_record.get("mathlib_revision")
            if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
                errors.append(f"BOUNDARY_COST_GATE: {name} lacks an exact Mathlib revision")
            installed_identity = _installed_mathlib_identity(base_dir)
            if installed_identity is None:
                errors.append(f"BOUNDARY_COST_GATE: {name} cannot resolve a clean official pinned Mathlib checkout")
            else:
                installed_revision, lake_manifest_hash = installed_identity
                if revision != installed_revision:
                    errors.append(f"BOUNDARY_COST_GATE: {name} Mathlib revision does not match the campaign checkout")
                if cost_record.get("lake_manifest_sha256") != lake_manifest_hash:
                    errors.append(f"BOUNDARY_COST_GATE: {name} cost record does not bind the campaign lake manifest")
            queries = cost_record.get("mathlib_queries")
            if not isinstance(queries, list) or not queries or any(
                not _substantive_string(item) for item in queries
            ):
                errors.append(f"BOUNDARY_COST_GATE: {name} lacks concrete Mathlib queries")
            _, search_payload = _evidence_path(
                cost_record.get("mathlib_search_transcript"), base_dir,
                f"boundary {name}.mathlib_search_transcript", errors,
            )
            if search_payload is not None:
                try:
                    search_text = search_payload.decode("utf-8")
                except UnicodeDecodeError:
                    errors.append(f"BOUNDARY_COST_GATE: {name} Mathlib search transcript is not UTF-8")
                else:
                    if len(search_text.strip()) < 40:
                        errors.append(f"BOUNDARY_COST_GATE: {name} Mathlib search transcript is content-free")
                    elif isinstance(queries, list) and any(query not in search_text for query in queries):
                        errors.append(f"BOUNDARY_COST_GATE: {name} Mathlib queries are absent from the transcript")
            attempts = cost_record.get("attempted_routes")
            if not isinstance(attempts, list) or len(attempts) < 2:
                errors.append(f"BOUNDARY_COST_GATE: {name} requires at least two recorded proof/formalization routes")
            else:
                route_names: set[str] = set()
                attempt_evidence_hashes: set[str] = set()
                for index, attempt in enumerate(attempts):
                    if (
                        not isinstance(attempt, dict)
                        or not _substantive_string(attempt.get("route"))
                        or not _substantive_string(attempt.get("outcome"))
                    ):
                        errors.append(f"BOUNDARY_COST_GATE: {name} attempted_routes[{index}] is incomplete")
                        continue
                    route_key = " ".join(attempt["route"].casefold().split())
                    if route_key in route_names:
                        errors.append(f"BOUNDARY_COST_GATE: {name} attempted routes are not distinct")
                    route_names.add(route_key)
                    evidence_ref = attempt.get("evidence")
                    evidence_hash = evidence_ref.get("sha256") if isinstance(evidence_ref, dict) else None
                    if evidence_hash in attempt_evidence_hashes:
                        errors.append(f"BOUNDARY_COST_GATE: {name} attempted routes reuse the same evidence")
                    if isinstance(evidence_hash, str):
                        attempt_evidence_hashes.add(evidence_hash)
                    _, attempt_payload = _evidence_path(
                        evidence_ref, base_dir,
                        f"boundary {name}.attempted_routes[{index}].evidence", errors,
                    )
                    if attempt_payload is not None and len(attempt_payload.strip()) < 40:
                        errors.append(f"BOUNDARY_COST_GATE: {name} attempted_routes[{index}] evidence is content-free")
            if cost_record.get("decision") != "disproportionate_to_campaign_role":
                errors.append(f"BOUNDARY_COST_GATE: {name} was not deferred on the required relative-cost basis")
            for field in ("campaign_role", "estimated_formalization_scope", "justification"):
                if not _substantive_string(cost_record.get(field)):
                    errors.append(f"BOUNDARY_COST_GATE: {name} lacks {field}")

        decision_audits = cost.get("independent_decision_audits")
        if not isinstance(decision_audits, list) or len(decision_audits) < 2:
            errors.append(f"BOUNDARY_COST_GATE: {name} requires two independent cost-decision audits")
        else:
            decision_auditors: set[str] = set()
            source_auditors = {
                _identity_key(audit.get("auditor")) for audit in assumption.get("independent_source_audits", [])
                if isinstance(audit, dict) and _nonempty_string(audit.get("auditor"))
            }
            cost_hash = cost.get("record", {}).get("sha256") if isinstance(cost.get("record"), dict) else None
            required_cost_findings = {
                "standardness", "mathlib_absence", "attempts", "relative_cost", "boundary_appropriateness",
            }
            for index, audit in enumerate(decision_audits):
                label = f"boundary {name}.independent_decision_audits[{index}]"
                if not isinstance(audit, dict):
                    errors.append(f"BOUNDARY_COST_GATE: {label} must be an object")
                    continue
                auditor = audit.get("auditor")
                auditor_key = _identity_key(auditor)
                if (
                    not _nonempty_string(auditor)
                    or auditor_key == _identity_key(manifest_author)
                    or auditor_key == _identity_key(gold_auditor)
                    or auditor_key in source_auditors
                    or auditor_key in decision_auditors
                ):
                    errors.append(f"BOUNDARY_COST_GATE: {label} has an invalid auditor")
                else:
                    decision_auditors.add(auditor_key)
                if audit.get("status") != "passed":
                    errors.append(f"BOUNDARY_COST_GATE: {label} did not pass")
                report = _json_evidence(audit.get("report"), base_dir, f"{label}.report", errors)
                findings = report.get("findings") if report is not None else None
                if (
                    report is None
                    or report.get("verdict") != "passed"
                    or report.get("boundary_id") != assumption.get("id")
                    or report.get("auditor") != auditor
                    or report.get("source_sha256") != assumption.get("source_evidence", {}).get("sha256")
                    or report.get("cost_record_sha256") != cost_hash
                    or not isinstance(findings, dict)
                    or set(findings) != required_cost_findings
                    or any(not _substantive_string(findings.get(key)) for key in required_cost_findings)
                ):
                    errors.append(f"BOUNDARY_COST_GATE: {label} structured report is incomplete")

    source_path, payload = _evidence_path(
        assumption.get("source_evidence"), base_dir, f"boundary {name}.source_evidence", errors,
    )
    quote = assumption.get("source_quote")
    locator = assumption.get("source_locator")
    if not _nonempty_string(quote):
        errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {name} lacks a verbatim source_quote")
    if not isinstance(locator, dict):
        errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {name} lacks a structured source_locator")
    elif (
        not _nonempty_string(locator.get("label"))
        or not isinstance(locator.get("line_start"), int)
        or not isinstance(locator.get("line_end"), int)
        or locator["line_start"] < 1
        or locator["line_end"] < locator["line_start"]
    ):
        errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {name} has an invalid source_locator")
    if payload is not None and _nonempty_string(quote):
        try:
            source_text = payload.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"EVIDENCE_INVALID: boundary source for {name} is not UTF-8 text")
        else:
            if quote not in source_text:
                errors.append(f"SOURCE_QUOTE_MISMATCH: {name} quote is absent from the hashed source")
            if isinstance(locator, dict) and isinstance(locator.get("line_start"), int) and isinstance(locator.get("line_end"), int):
                lines = source_text.splitlines()
                start = locator["line_start"] - 1
                end = locator["line_end"]
                if start < 0 or end > len(lines) or quote not in "\n".join(lines[start:end]):
                    errors.append(f"SOURCE_LOCATOR_MISMATCH: {name} quote is not at the claimed lines")
    if source_path is not None and base_dir is not None:
        parts = source_path.relative_to(base_dir.resolve()).parts
        if not parts or parts[0] not in {"ref", "refs"}:
            errors.append(f"SOURCE_OUTSIDE_REF: {name} source must be under manifest-local ref/ or refs/")

    notation = assumption.get("notation_map")
    if not isinstance(notation, list) or not notation:
        errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {name} notation_map must not be empty")
    else:
        for index, item in enumerate(notation):
            if (
                not isinstance(item, dict)
                or not _nonempty_string(item.get("source"))
                or not _nonempty_string(item.get("lean"))
            ):
                errors.append(
                    f"BOUNDARY_AUDIT_INCOMPLETE: {name}.notation_map[{index}] is incomplete"
                )
    _exact_checklist(assumption.get("hypothesis_checklist"), f"{name}.hypothesis_checklist", errors)
    _exact_checklist(assumption.get("conclusion_checklist"), f"{name}.conclusion_checklist", errors)

    audits = assumption.get("independent_source_audits")
    if not isinstance(audits, list) or len(audits) < 2:
        errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {name} requires two independent source audits")
        return
    auditors: set[str] = set()
    for index, audit in enumerate(audits):
        label = f"boundary {name}.independent_source_audits[{index}]"
        if not isinstance(audit, dict):
            errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {label} must be an object")
            continue
        auditor = audit.get("auditor")
        auditor_key = _identity_key(auditor)
        if (
            not _nonempty_string(auditor)
            or auditor_key == _identity_key(manifest_author)
            or auditor_key in auditors
        ):
            errors.append(f"BOUNDARY_AUDIT_NOT_INDEPENDENT: {label} has an invalid auditor")
        else:
            auditors.add(auditor_key)
        if audit.get("status") != "passed":
            errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {label} did not pass")
        report = _json_evidence(audit.get("report"), base_dir, f"{label}.report", errors)
        required_findings = {"source_match", "hypotheses", "conclusion", "notation", "use_site"}
        findings = report.get("findings") if report is not None else None
        if (
            report is None
            or report.get("verdict") != "passed"
            or report.get("boundary_id") != assumption.get("id")
            or report.get("auditor") != auditor
            or report.get("source_sha256") != assumption.get("source_evidence", {}).get("sha256")
            or report.get("lean_binder") != assumption.get("lean_binder")
            or not isinstance(findings, dict)
            or set(findings) != required_findings
            or any(not _substantive_string(findings.get(key)) for key in required_findings)
        ):
            errors.append(f"BOUNDARY_AUDIT_INCOMPLETE: {label} structured report is incomplete")


def audit_manifest(
    data: dict[str, Any],
    base_dir: Path | None = None,
    *,
    kernel_runtime_verified: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["SCHEMA_INVALID: manifest must be a JSON object"]
    grade = data.get("grade")
    if grade not in GRADES:
        if isinstance(grade, str) and grade.startswith("GOLD-"):
            errors.append("GRADE_VARIANT: GOLD-* variants are forbidden")
        else:
            errors.append("GRADE_INVALID: grade must be BRONZE, SILVER, or GOLD")
        return errors
    if grade != "GOLD":
        return errors

    required = {
        "schema_version", "manifest_author", "target_contract", "kernel_evidence",
        "axioms", "assumptions", "interfaces", "theorem_faces",
        "definition_independence", "independent_gold_audit",
    }
    for key in sorted(required - data.keys()):
        errors.append(f"SCHEMA_MISSING: GOLD manifest requires {key}")
    schema_version_value = data.get("schema_version")
    if schema_version_value not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"SCHEMA_VERSION: expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    schema_version = (
        schema_version_value if schema_version_value in SUPPORTED_SCHEMA_VERSIONS else 1
    )
    author = data.get("manifest_author")
    if not _nonempty_string(author):
        errors.append("SCHEMA_INVALID: manifest_author must be non-empty")
    result_scope = data.get("result_scope") if schema_version >= 2 else "unconditional"
    question_status = data.get("question_status")
    research_value = data.get("research_value")
    goal_linked = schema_version >= 2 and (
        question_status in {"settled", "conditional_advance"}
        or research_value == "advances_question"
    )
    if schema_version >= 2 and result_scope not in {"conditional", "unconditional"}:
        errors.append("SCHEMA_INVALID: result_scope must be conditional or unconditional")
    if schema_version >= 2:
        if question_status not in {
            "settled", "conditional_advance", "interface_lemma", "no_progress",
        }:
            errors.append("SCHEMA_INVALID: question_status is required for schema-v2 Gold")
        if research_value not in {
            "advances_question", "supporting_result", "tautological", "no_progress",
        }:
            errors.append("SCHEMA_INVALID: research_value is required for schema-v2 Gold")
        if result_scope == "conditional" and question_status == "settled":
            errors.append("RESEARCH_SCOPE_OVERCLAIM: conditional Gold cannot settle the question")
        if (
            question_status in {"interface_lemma", "no_progress"}
            and research_value == "advances_question"
        ):
            errors.append("RESEARCH_SCOPE_OVERCLAIM: interface/no-progress result cannot claim an advance")
        if not kernel_runtime_verified:
            errors.append("KERNEL_RUNTIME_UNVERIFIED: run the heavy audit CLI, not metadata-only audit")

    contract = _json_evidence(data.get("target_contract"), base_dir, "target_contract", errors)
    kernel = _json_evidence(data.get("kernel_evidence"), base_dir, "kernel_evidence", errors)

    contract_original: set[str] = set()
    contract_conditions: set[str] = set()
    contract_boundary: set[str] = set()
    contract_data: set[str] = set()
    contract_faces: set[str] = set()
    contract_interfaces: set[str] = set()
    contract_intended_binders: set[str] = set()
    target_hash: str | None = None
    if contract is not None:
        if contract.get("schema_version") != schema_version:
            errors.append(f"CONTRACT_SCHEMA_VERSION: expected {schema_version}")
        target_hash = contract.get("target_signature_hash")
        dossier_hash = contract.get("dossier_signature_hash")
        target_signature = contract.get("target_signature")
        dossier_signature = contract.get("dossier_signature")
        if not isinstance(target_hash, str) or not _SHA256.fullmatch(target_hash):
            errors.append("TARGET_MISMATCH: contract target_signature_hash must be sha256")
        if target_hash != dossier_hash:
            errors.append("TARGET_MISMATCH: target and dossier signature hashes differ")
        if not _nonempty_string(target_signature) or not _nonempty_string(dossier_signature):
            errors.append("TARGET_MISMATCH: contract must contain both canonical signatures")
        else:
            computed_target = hashlib.sha256(target_signature.encode()).hexdigest()
            computed_dossier = hashlib.sha256(dossier_signature.encode()).hexdigest()
            if computed_target != target_hash or computed_dossier != dossier_hash:
                errors.append("TARGET_MISMATCH: canonical signature text does not match its hash")
        contract_original = set(_string_ids(
            contract.get("original_premise_ids"), "target_contract.original_premise_ids", errors,
        ))
        if schema_version >= 2:
            contract_data = set(_string_ids(
                contract.get("data_binder_ids"),
                "target_contract.data_binder_ids", errors,
            ))
            if goal_linked:
                contract_intended_binders = set(_string_ids(
                    contract.get("intended_model_binder_ids"),
                    "target_contract.intended_model_binder_ids", errors,
                ))
                if not contract_intended_binders.issubset(contract_data):
                    errors.append(
                        "INTENDED_MODEL_BINDING_INVALID: intended model binders must be data binders"
                    )
            structural_binders = _string_ids(
                contract.get("structural_binders"),
                "target_contract.structural_binders", errors,
            )
            canonical_instance_types = _instance_type_census(contract, errors)
            _elaboration_context(contract, errors)
            if _nonempty_string(target_signature):
                extracted = _top_level_square_binders(target_signature)
                if structural_binders != extracted:
                    errors.append(
                        "STRUCTURAL_CONTEXT_MISMATCH: contract must enumerate every explicit instance binder in signature order"
                    )
                for binder in structural_binders:
                    words = binder[1:-1].strip().split()
                    class_name = words[0] if words else ""
                    if class_name not in STRUCTURAL_CLASS_ALLOWLIST and canonical_instance_types is None:
                        errors.append(
                            f"STRUCTURAL_CONTEXT_UNAUDITED: {binder} is not an approved ambient structure; expose its proposition fields as premises or an interface"
                        )
            if _nonempty_string(dossier_signature):
                dossier_structural = _top_level_square_binders(dossier_signature)
                if structural_binders != dossier_structural:
                    errors.append(
                        "STRUCTURAL_CONTEXT_MISMATCH: dossier and contract structural context differ"
                    )
            contract_conditions = set(_string_ids(
                contract.get("condition_premise_ids"),
                "target_contract.condition_premise_ids", errors,
            ))
            contract_boundary = set(_string_ids(
                contract.get("boundary_premise_ids"),
                "target_contract.boundary_premise_ids", errors,
            ))
            if (
                contract_original & contract_conditions
                or contract_original & contract_boundary
                or contract_conditions & contract_boundary
            ):
                errors.append("PREMISE_CLASS_MISMATCH: public premise classes must be disjoint")
            explicit_names, implicit_names = _top_level_named_binders(target_signature)
            named_binders = explicit_names + implicit_names
            if len(named_binders) != len(set(named_binders)) or "<anonymous>" in named_binders:
                errors.append("BINDER_CENSUS_INVALID: named theorem binders must be unique and non-anonymous")
            expected_named = contract_data | contract_original | contract_conditions | contract_boundary
            logical_instances = _instance_premises(
                contract, contract_original | contract_conditions | contract_boundary, errors,
            )
            instance_ids = {entry["premise_id"] for entry in logical_instances.values()}
            if instance_ids & set(named_binders):
                errors.append("BINDER_CENSUS_INVALID: instance premise ids must not alias named binders")
            if set(named_binders) | instance_ids != expected_named:
                errors.append("BINDER_CENSUS_INCOMPLETE: data and public premise ids must partition every named theorem binder")
            if contract.get("result_scope") != result_scope:
                errors.append("TARGET_MISMATCH: manifest and contract result_scope differ")
        contract_faces = set(_string_ids(
            contract.get("theorem_face_ids"), "target_contract.theorem_face_ids", errors,
            nonempty=True,
        ))
        contract_interfaces = set(_string_ids(
            contract.get("interface_ids"), "target_contract.interface_ids", errors,
        ))
        source_files = contract.get("source_files")
        source_payloads: list[bytes] = []
        if not isinstance(source_files, list) or not source_files:
            errors.append("SCHEMA_INVALID: target_contract.source_files must not be empty")
        else:
            contract_path, _ = _evidence_path(
                data.get("target_contract"), base_dir, "target_contract", [],
            )
            contract_dir = contract_path.parent if contract_path is not None else None
            for index, source in enumerate(source_files):
                _, payload = _evidence_path(source, contract_dir, f"target source[{index}]", errors)
                if payload is not None:
                    source_payloads.append(payload)
        if schema_version >= 2 and _nonempty_string(target_signature):
            if not any(target_signature.encode() in payload for payload in source_payloads):
                errors.append("TARGET_SOURCE_MISMATCH: frozen signature is absent from target sources")

    root_names: set[str] = set()
    kernel_roots: list[dict[str, Any]] = []
    kernel_premises: set[str] = set()
    kernel_faces: set[str] = set()
    kernel_interfaces: set[str] = set()
    kernel_axioms: set[str] = set()
    if kernel is not None:
        if kernel.get("schema_version") != schema_version:
            errors.append(f"KERNEL_SCHEMA_VERSION: expected {schema_version}")
        if target_hash is not None and kernel.get("target_signature_hash") != target_hash:
            errors.append("TARGET_MISMATCH: kernel evidence is for a different signature")
        roots = kernel.get("root_declarations")
        if not isinstance(roots, list) or not roots:
            errors.append("SCHEMA_INVALID: kernel_evidence.root_declarations must not be empty")
        else:
            exact_root = False
            for index, root in enumerate(roots):
                label = f"kernel root[{index}]"
                if not isinstance(root, dict):
                    errors.append(f"SCHEMA_INVALID: {label} must be an object")
                    continue
                name = root.get("name")
                if not _nonempty_string(name):
                    errors.append(f"SCHEMA_INVALID: {label}.name must be non-empty")
                else:
                    if name in root_names:
                        errors.append(f"SCHEMA_INVALID: duplicate kernel root name {name}")
                    root_names.add(name)
                kernel_roots.append(root)
                if root.get("proof_status") != "completed":
                    errors.append(f"PROOF_OPEN: {name or label} is not completed")
                signature_text = root.get("signature")
                signature_hash = root.get("signature_hash")
                if not _nonempty_string(signature_text) or not isinstance(signature_hash, str):
                    errors.append(f"SCHEMA_INVALID: {label} requires signature text and hash")
                elif hashlib.sha256(signature_text.encode()).hexdigest() != signature_hash:
                    errors.append(f"TARGET_MISMATCH: {label} signature text/hash disagree")
                _elaboration_context(root, errors)
                root_canonical_types = _instance_type_census(root, errors)
                _instance_premises(root, set(root.get("premise_ids", [])), errors)
                if root_canonical_types is not None:
                    if root.get("structural_binders", []) != _top_level_square_binders(signature_text):
                        errors.append(f"STRUCTURAL_CONTEXT_MISMATCH: {label} must enumerate exact square binders")
                if target_hash is not None and signature_hash == target_hash:
                    exact_root = True
                root_axioms = root.get("axioms")
                if not isinstance(root_axioms, list) or any(not _nonempty_string(x) for x in root_axioms):
                    errors.append(f"SCHEMA_INVALID: {label}.axioms must be a string list")
                else:
                    kernel_axioms.update(root_axioms)
                    extra = set(root_axioms) - STANDARD_AXIOMS
                    if extra:
                        errors.append("AXIOMS_OPEN: " + ", ".join(sorted(extra)))
                kernel_premises.update(_string_ids(root.get("premise_ids"), f"{label}.premise_ids", errors))
                kernel_faces.update(_string_ids(root.get("theorem_face_ids"), f"{label}.theorem_face_ids", errors))
                kernel_interfaces.update(_string_ids(root.get("interface_ids"), f"{label}.interface_ids", errors))
                _decl_in_file(
                    name, root.get("lean_file"), base_dir, f"{label}.lean_file", errors,
                    signature_text if _nonempty_string(signature_text) else None,
                )
            if target_hash is not None and not exact_root:
                errors.append("TARGET_MISMATCH: no completed root has the frozen target signature")
    if schema_version >= 2 and contract is not None:
        expected_public = contract_original | contract_conditions | contract_boundary
        for root in kernel_roots:
            if root.get("signature_hash") != target_hash:
                continue
            for field in ("instance_premises", "instance_binder_types", "elaboration_context",
                          "elaboration_context_sha256"):
                if root.get(field) != contract.get(field):
                    errors.append(f"ROOT_BINDER_CONTEXT_MISMATCH: frozen root and contract differ in {field}")
            if set(root.get("premise_ids", [])) != expected_public:
                errors.append(
                    "ROOT_PREMISE_MISMATCH: frozen target root must use exactly the target contract premises"
                )
            if set(root.get("interface_ids", [])) != contract_interfaces:
                errors.append(
                    "ROOT_INTERFACE_MISMATCH: frozen target root must use exactly the target contract interfaces"
                )
            if set(root.get("theorem_face_ids", [])) != contract_faces:
                errors.append(
                    "ROOT_FACE_MISMATCH: frozen target root must cover exactly the target contract theorem faces"
                )

    axioms = data.get("axioms")
    if not isinstance(axioms, list) or any(not _nonempty_string(item) for item in axioms):
        errors.append("SCHEMA_INVALID: axioms must be a list of strings")
        manifest_axioms: set[str] = set()
    else:
        manifest_axioms = set(axioms)
        extra = manifest_axioms - STANDARD_AXIOMS
        if extra:
            errors.append("AXIOMS_OPEN: " + ", ".join(sorted(extra)))
        if kernel is not None and manifest_axioms != kernel_axioms:
            errors.append("AXIOM_EVIDENCE_MISMATCH: manifest and kernel roots differ")

    assumptions = data.get("assumptions")
    assumption_ids: set[str] = set()
    if not isinstance(assumptions, list):
        errors.append("SCHEMA_INVALID: assumptions must be a list")
    else:
        for index, assumption in enumerate(assumptions):
            if not isinstance(assumption, dict):
                errors.append(f"SCHEMA_INVALID: assumption[{index}] must be an object")
                continue
            premise_id = assumption.get("id")
            name = assumption.get("name", "<unnamed>")
            kind = assumption.get("kind")
            status = assumption.get("status")
            relation = assumption.get("relation_to_goal")
            if not _nonempty_string(premise_id) or premise_id in assumption_ids:
                errors.append(f"SCHEMA_INVALID: assumption id missing/duplicate at {name}")
            else:
                assumption_ids.add(premise_id)
            if not _nonempty_string(name):
                errors.append(f"SCHEMA_INVALID: assumption {premise_id} needs a name")
            if kind == "condition" and status != "declared":
                errors.append(f"UNRESOLVED_PREMISE: {name} (condition/{status})")
            elif kind not in {"boundary", "condition"} and status != "closed":
                errors.append(f"UNRESOLVED_PREMISE: {name} ({kind}/{status})")
            allowed_kinds = {"original", "derived"} | (
                {"boundary", "condition"} if schema_version >= 2 else set()
            )
            if kind not in allowed_kinds:
                errors.append(f"UNAUTHORIZED_PREMISE: {name} ({kind})")
            if relation not in {"none", *BAD_RELATIONS}:
                errors.append(f"SCHEMA_INVALID: {name} has unknown relation_to_goal")
            if relation in BAD_RELATIONS:
                code = "CARRIER_COLLAPSE" if relation == "carrier_collapse" else "GOAL_SHAPED_PREMISE"
                errors.append(f"{code}: {name} ({relation})")
            if kind == "original":
                if premise_id not in contract_original:
                    errors.append(f"FAKE_ORIGINAL_PREMISE: {name} is not in the frozen target")
                if not _nonempty_string(assumption.get("source_locator")):
                    errors.append(f"SOURCE_LOCATOR_MISSING: original premise {name}")
                if schema_version >= 2:
                    if assumption.get("exposure") != "direct_binder":
                        errors.append(f"HIDDEN_CONDITION: original premise {name} is not a direct theorem binder")
                    if not _nonempty_string(assumption.get("lean_binder")):
                        errors.append(f"HIDDEN_CONDITION: original premise {name} lacks exact lean_binder text")
            if kind == "derived":
                if premise_id in contract_original:
                    errors.append(f"PREMISE_CLASS_MISMATCH: {name} is frozen as original")
                if assumption.get("proof_status") != "completed":
                    errors.append(f"DERIVATION_MISSING: {name} is not completed")
                _decl_in_file(
                    assumption.get("lean_decl"), assumption.get("lean_file"), base_dir,
                    f"derived premise {name}.lean_file", errors,
                )
            if kind == "condition":
                if premise_id not in contract_conditions:
                    errors.append(f"FAKE_DECLARED_CONDITION: {name} is not in the frozen target")
                if assumption.get("exposure") != "direct_binder":
                    errors.append(f"HIDDEN_CONDITION: declared condition {name} is not a direct theorem binder")
                if not _nonempty_string(assumption.get("lean_binder")):
                    errors.append(f"HIDDEN_CONDITION: declared condition {name} lacks exact lean_binder text")
                if not _nonempty_string(assumption.get("introduction_rationale")):
                    errors.append(f"CONDITION_RATIONALE_MISSING: {name} needs an honest scope rationale")
            if kind == "boundary":
                if premise_id not in contract_boundary:
                    errors.append(f"FAKE_BOUNDARY_PREMISE: {name} is not in the frozen target")
                gold_audit = data.get("independent_gold_audit")
                gold_auditor = gold_audit.get("auditor") if isinstance(gold_audit, dict) else None
                _audit_boundary_assumption(
                    assumption,
                    assumptions if isinstance(assumptions, list) else [],
                    base_dir, author, gold_auditor, errors,
                )
    if contract is not None and not (
        contract_original | contract_conditions | contract_boundary
    ).issubset(assumption_ids):
        errors.append("PREMISE_CENSUS_INCOMPLETE: frozen public premises are missing")
    if schema_version >= 2:
        public_ids = contract_original | contract_conditions | contract_boundary
        if result_scope == "unconditional" and public_ids:
            errors.append("SCOPE_MISMATCH: unconditional Gold cannot have proposition premises")
        if result_scope == "conditional" and not public_ids:
            errors.append("SCOPE_MISMATCH: conditional Gold needs at least one public antecedent")
    if schema_version >= 2 and assumption_ids:
        for assumption in assumptions if isinstance(assumptions, list) else []:
            if not isinstance(assumption, dict) or assumption.get("kind") == "derived":
                continue
            premise_id = assumption.get("id")
            binder = assumption.get("lean_binder")
            for root in kernel_roots:
                if premise_id in root.get("premise_ids", []):
                    signature = _signature_binder_prefix(root.get("signature", ""))
                    if not _nonempty_string(binder) or binder not in signature:
                        errors.append(
                            f"HIDDEN_CONDITION: {assumption.get('name', premise_id)} is not exposed verbatim in root {root.get('name', '<unnamed>')}"
                        )
    if kernel is not None and assumption_ids != kernel_premises:
        errors.append("PREMISE_EVIDENCE_MISMATCH: manifest and kernel roots differ")

    interfaces = data.get("interfaces")
    interface_ids: set[str] = set()
    if not isinstance(interfaces, list):
        errors.append("SCHEMA_INVALID: interfaces must be a list")
    else:
        for index, interface in enumerate(interfaces):
            if not isinstance(interface, dict):
                errors.append(f"SCHEMA_INVALID: interface[{index}] must be an object")
                continue
            interface_id = interface.get("id")
            name = interface.get("name", "<unnamed>")
            if not _nonempty_string(interface_id) or interface_id in interface_ids:
                errors.append(f"SCHEMA_INVALID: interface id missing/duplicate at {name}")
            else:
                interface_ids.add(interface_id)
            intended = interface.get("intended_instance")
            if not isinstance(intended, dict):
                errors.append(f"NO_INTENDED_INSTANCE: {name} requires adapter evidence")
                continue
            if intended.get("proof_status") != "completed":
                errors.append(f"NO_INTENDED_INSTANCE: {name} adapter is not completed")
            adapter_axioms = intended.get("axioms")
            if not isinstance(adapter_axioms, list) or set(adapter_axioms) - STANDARD_AXIOMS:
                errors.append(f"NO_INTENDED_INSTANCE: {name} adapter has open/invalid axioms")
            _decl_in_file(
                intended.get("adapter_decl"), intended.get("lean_file"), base_dir,
                f"interface {name}.lean_file", errors,
            )
    if contract is not None and interface_ids != contract_interfaces:
        errors.append("INTERFACE_CENSUS_MISMATCH: manifest and target contract differ")
    if kernel is not None and interface_ids != kernel_interfaces:
        errors.append("INTERFACE_EVIDENCE_MISMATCH: manifest and kernel roots differ")

    goal_object_ids: set[str] = set()
    goal_face_ids: set[str] = set()
    goal_id: str | None = None
    goal_contract = None
    goal_contract_ref = data.get("goal_contract")
    if goal_linked or goal_contract_ref is not None:
        if goal_contract_ref is None:
            errors.append("GOAL_ALIGNMENT_MISSING: a question-level claim requires a frozen goal contract")
        else:
            goal_contract = _json_evidence(
                goal_contract_ref, base_dir, "goal_contract", errors,
            )
    if goal_contract is not None:
        if goal_contract.get("schema_version") != schema_version:
            errors.append(f"GOAL_CONTRACT_SCHEMA_VERSION: expected {schema_version}")
        goal_id = goal_contract.get("goal_id")
        if not _nonempty_string(goal_id):
            errors.append("GOAL_CONTRACT_INVALID: goal_id must be non-empty")
        if not _substantive_string(goal_contract.get("question")):
            errors.append("GOAL_CONTRACT_INVALID: question must be substantive")
        if not _substantive_string(goal_contract.get("answer_criterion")):
            errors.append("GOAL_CONTRACT_INVALID: answer_criterion must be substantive")
        intended_objects = goal_contract.get("intended_objects")
        if not isinstance(intended_objects, list) or not intended_objects:
            errors.append("GOAL_CONTRACT_INVALID: intended_objects must not be empty")
        else:
            for index, intended_object in enumerate(intended_objects):
                if not isinstance(intended_object, dict):
                    errors.append(f"GOAL_CONTRACT_INVALID: intended_objects[{index}] must be an object")
                    continue
                object_id = intended_object.get("id")
                if not _nonempty_string(object_id) or object_id in goal_object_ids:
                    errors.append("GOAL_CONTRACT_INVALID: intended object id missing/duplicate")
                else:
                    goal_object_ids.add(object_id)
                if not _substantive_string(intended_object.get("description")):
                    errors.append(
                        f"GOAL_CONTRACT_INVALID: intended object {object_id or index} needs a substantive description"
                    )
        goal_face_ids = set(_string_ids(
            goal_contract.get("goal_theorem_face_ids"),
            "goal_contract.goal_theorem_face_ids", errors, nonempty=True,
        ))
        goal_contract_path, _ = _evidence_path(
            goal_contract_ref, base_dir, "goal_contract", [],
        )
        _, question_payload = _evidence_path(
            goal_contract.get("question_source"),
            goal_contract_path.parent if goal_contract_path is not None else None,
            "goal_contract.question_source", errors,
        )
        if (
            question_payload is not None
            and _nonempty_string(goal_contract.get("question"))
            and goal_contract["question"].encode() not in question_payload
        ):
            errors.append("GOAL_SOURCE_MISMATCH: frozen question is absent from its hashed source")

    alignment_ref = data.get("goal_alignment")
    alignment = None
    if goal_linked or alignment_ref is not None:
        if not isinstance(alignment_ref, dict) or alignment_ref.get("status") != "passed":
            errors.append("GOAL_ALIGNMENT_MISSING: a question-level claim requires a passed alignment audit")
        else:
            alignment = _json_evidence(
                alignment_ref.get("report"), base_dir, "goal_alignment.report", errors,
            )
            alignment_auditor = alignment_ref.get("auditor")
            gold_audit = data.get("independent_gold_audit")
            gold_auditor = gold_audit.get("auditor") if isinstance(gold_audit, dict) else None
            if (
                not _nonempty_string(alignment_auditor)
                or _identity_key(alignment_auditor) in {
                    _identity_key(author), _identity_key(gold_auditor),
                }
            ):
                errors.append(
                    "GOAL_ALIGNMENT_NOT_INDEPENDENT: alignment auditor must differ from author and Gold auditor"
                )
            required_findings = {
                "target_match", "consumer_path", "directionality", "intended_objects",
            }
            findings = alignment.get("findings") if alignment is not None else None
            classification = alignment.get("classification") if alignment is not None else None
            directionality = alignment.get("directionality") if alignment is not None else None
            consumer_path = alignment.get("consumer_path") if alignment is not None else None
            valid_path = (
                isinstance(consumer_path, list)
                and bool(consumer_path)
                and all(_nonempty_string(item) for item in consumer_path)
                and consumer_path[-1] in goal_face_ids
            )
            expected_classification = {
                "settled": {"settles_goal": "iff"},
                "conditional_advance": {
                    "sufficient_milestone": "sufficient_only",
                    "necessary_milestone": "necessary_only",
                },
                "interface_lemma": {"supporting": "none", "terminal": "none"},
                "no_progress": {"supporting": "none", "terminal": "none"},
            }.get(question_status, {})
            if (
                alignment is None
                or alignment.get("verdict") != "passed"
                or alignment.get("auditor") != alignment_auditor
                or alignment.get("goal_id") != goal_id
                or alignment.get("goal_contract_sha256") != (
                    goal_contract_ref.get("sha256") if isinstance(goal_contract_ref, dict) else None
                )
                or alignment.get("target_signature_hash") != target_hash
                or classification not in expected_classification
                or directionality != expected_classification.get(classification)
                or not valid_path
                or not isinstance(findings, dict)
                or set(findings) != required_findings
                or any(not _substantive_string(findings.get(key)) for key in required_findings)
            ):
                errors.append("GOAL_ALIGNMENT_INVALID: structured goal-path evidence is incomplete or overclaims")

    bindings = data.get("intended_model_bindings")
    goal_evidenced = goal_contract is not None or alignment is not None
    if (goal_linked or goal_evidenced) and not isinstance(bindings, list):
        errors.append("INTENDED_MODEL_BINDING_MISSING: goal-aligned roots require intended-model bindings")
    elif bindings is not None:
        if not isinstance(bindings, list):
            errors.append("SCHEMA_INVALID: intended_model_bindings must be a list")
        else:
            covered_objects: set[str] = set()
            covered_binders: set[str] = set()
            for index, binding in enumerate(bindings):
                label = f"intended_model_bindings[{index}]"
                if not isinstance(binding, dict):
                    errors.append(f"SCHEMA_INVALID: {label} must be an object")
                    continue
                object_id = binding.get("goal_object_id")
                if not _nonempty_string(object_id) or object_id not in goal_object_ids:
                    errors.append(f"INTENDED_MODEL_BINDING_INVALID: {label} has an unknown goal object")
                elif object_id in covered_objects:
                    errors.append(f"INTENDED_MODEL_BINDING_INVALID: goal object {object_id} is bound twice")
                else:
                    covered_objects.add(object_id)
                if binding.get("status") != "completed":
                    errors.append(f"INTENDED_MODEL_BINDING_INVALID: {label} is not completed")
                binder_ids = set(_string_ids(binding.get("binder_ids"), f"{label}.binder_ids", errors))
                if not binder_ids.issubset(contract_intended_binders):
                    errors.append(f"INTENDED_MODEL_BINDING_INVALID: {label} names unaudited binders")
                if covered_binders & binder_ids:
                    errors.append(f"INTENDED_MODEL_BINDING_INVALID: {label} reuses a binder")
                covered_binders.update(binder_ids)
                _decl_in_file(
                    binding.get("adapter_decl"), binding.get("lean_file"), base_dir,
                    f"{label}.lean_file", errors,
                )
                if binding.get("adapter_decl") in root_names:
                    errors.append(
                        f"INTENDED_MODEL_BINDING_INVALID: {label} adapter cannot be a theorem root"
                    )
            if (goal_linked or goal_evidenced) and covered_objects != goal_object_ids:
                errors.append("INTENDED_MODEL_BINDING_INCOMPLETE: every intended goal object must be bound")
            if (goal_linked or goal_evidenced) and covered_binders != contract_intended_binders:
                errors.append("INTENDED_MODEL_BINDING_INCOMPLETE: every intended model binder must be bound")

    faces = data.get("theorem_faces")
    face_ids: set[str] = set()
    if not isinstance(faces, list) or not faces:
        errors.append("SCHEMA_INVALID: theorem_faces must not be empty")
    else:
        for index, face in enumerate(faces):
            if not isinstance(face, dict):
                errors.append(f"SCHEMA_INVALID: theorem_face[{index}] must be an object")
                continue
            face_id = face.get("id")
            name = face.get("name", "<unnamed>")
            if not _nonempty_string(face_id) or face_id in face_ids:
                errors.append(f"SCHEMA_INVALID: theorem face id missing/duplicate at {name}")
            else:
                face_ids.add(face_id)
            if face.get("covered") is not True:
                errors.append(f"THEOREM_FACE_OPEN: {name}")
            matching_roots = [root for root in kernel_roots if root.get("name") == face.get("lean_decl")]
            if len(matching_roots) != 1:
                errors.append(f"THEOREM_FACE_UNMAPPED: {name} has no audited root declaration")
            if schema_version >= 2:
                face_premises = set(_string_ids(
                    face.get("premise_ids"), f"theorem face {name}.premise_ids", errors,
                ))
                face_interfaces = set(_string_ids(
                    face.get("interface_ids"), f"theorem face {name}.interface_ids", errors,
                ))
                if len(matching_roots) == 1:
                    root = matching_roots[0]
                    if face_id not in root.get("theorem_face_ids", []):
                        errors.append(f"THEOREM_FACE_UNMAPPED: {name} is absent from its root")
                    if face_premises != set(root.get("premise_ids", [])):
                        errors.append(f"THEOREM_FACE_PREMISE_MISMATCH: {name}")
                    if face_interfaces != set(root.get("interface_ids", [])):
                        errors.append(f"THEOREM_FACE_INTERFACE_MISMATCH: {name}")
            if not _nonempty_string(face.get("source_locator")):
                errors.append(f"SOURCE_LOCATOR_MISSING: theorem face {name}")
    if contract is not None and face_ids != contract_faces:
        errors.append("THEOREM_FACE_CENSUS_MISMATCH: manifest and target contract differ")
    if kernel is not None and face_ids != kernel_faces:
        errors.append("THEOREM_FACE_EVIDENCE_MISMATCH: manifest and kernel roots differ")

    independence = data.get("definition_independence")
    if not isinstance(independence, dict) or independence.get("status") != "verified":
        errors.append("DEFINITION_DEPENDENCE: independent construction evidence required")
    elif schema_version >= 2:
        evidence = _json_evidence(
            independence.get("evidence"), base_dir, "definition_independence.evidence", errors,
        )
        required_checks = {
            "target_not_stored_as_field", "target_not_definitionally_encoded",
            "constructors_independent", "dependency_cone_reviewed",
        }
        if (
            evidence is None
            or evidence.get("verdict") != "verified"
            or evidence.get("target_signature_hash") != target_hash
            or set(evidence.get("checks", {}).keys()) != required_checks
            or not all(evidence.get("checks", {}).values())
            or set(evidence.get("findings", {}).keys()) != required_checks
            or any(
                not _substantive_string(evidence.get("findings", {}).get(key))
                for key in required_checks
            )
        ):
            errors.append("DEFINITION_DEPENDENCE: structured v2 evidence is incomplete")
    elif _evidence_path(
        independence.get("evidence"), base_dir, "definition_independence.evidence", errors,
    )[1] is None:
        errors.append("DEFINITION_DEPENDENCE: evidence is missing or stale")

    independent = data.get("independent_gold_audit")
    if not isinstance(independent, dict) or independent.get("status") != "passed":
        errors.append("GOLD_AUDIT_MISSING: independent semantic audit required")
    else:
        auditor = independent.get("auditor")
        if not _nonempty_string(auditor) or _identity_key(auditor) == _identity_key(author):
            errors.append("GOLD_AUDIT_NOT_INDEPENDENT: auditor must differ from manifest author")
        if schema_version >= 2:
            report = _json_evidence(
                independent.get("report"), base_dir, "independent_gold_audit.report", errors,
            )
            required_checks = {
                "target", "premises", "public_antecedents", "structural_context", "kernel_runtime",
                "interfaces", "theorem_faces", "definition_independence", "research_scope",
            }
            findings = report.get("findings") if report is not None else None
            if (
                report is None
                or report.get("verdict") != "passed"
                or report.get("target_signature_hash") != target_hash
                or report.get("auditor") != auditor
                or report.get("question_status") != data.get("question_status")
                or report.get("research_value") != data.get("research_value")
                or set(report.get("checks", {}).keys()) != required_checks
                or not all(report.get("checks", {}).values())
                or not isinstance(findings, dict)
                or set(findings) != required_checks
                or any(not _substantive_string(findings.get(key)) for key in required_checks)
            ):
                errors.append("GOLD_AUDIT_MISSING: structured v2 report is incomplete")
        else:
            report_path, report = _evidence_path(
                independent.get("report"), base_dir, "independent_gold_audit.report", errors,
            )
            if report_path is not None and report is not None and not report.strip():
                errors.append("GOLD_AUDIT_MISSING: independent report is empty")
    return errors


def record_audited_gold(
    data: dict[str, Any],
    base_dir: Path,
    manifest_path: Path,
    manifest_bytes: bytes,
    plan_data: Path,
    statement_id: str,
) -> list[str]:
    """Bind one successful schema-v2 Heavy audit to one completed target plan node."""
    errors: list[str] = []
    if data.get("grade") != "GOLD" or data.get("schema_version") != 2:
        return ["GOLD_RECORD_INVALID: only a passed schema-v2 GOLD manifest may be recorded"]
    try:
        parsed_manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"GOLD_RECORD_INVALID: manifest bytes are not valid JSON: {exc}"]
    if parsed_manifest != data:
        return ["GOLD_RECORD_INVALID: audited data do not equal the supplied manifest bytes"]
    if os.environ.get("PLAN_OFFLINE", "0") != "1":
        return [
            "GOLD_RECORD_INVALID: recording currently requires PLAN_OFFLINE=1; refusing to create a competing offline authority during an online run"
        ]
    if not _nonempty_string(statement_id):
        return ["GOLD_RECORD_INVALID: statement id is required"]
    manifest_path = manifest_path.resolve()
    base_dir = base_dir.resolve()
    if manifest_path.parent != base_dir:
        return ["GOLD_RECORD_INVALID: manifest path does not match the audited base directory"]
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        if manifest_path.read_bytes() != manifest_bytes:
            return ["GOLD_RECORD_STALE: manifest changed after it was audited"]
    except OSError as exc:
        return [f"GOLD_RECORD_STALE: cannot reread manifest: {exc}"]

    runtime_errors = verify_kernel_runtime(data, base_dir)
    errors.extend(runtime_errors)
    errors.extend(audit_manifest(
        data, base_dir, kernel_runtime_verified=not runtime_errors,
    ))
    if errors:
        return errors

    target = _json_evidence(data.get("target_contract"), base_dir, "gold record target", errors)
    kernel = _json_evidence(data.get("kernel_evidence"), base_dir, "gold record kernel", errors)
    alignment_ref = data.get("goal_alignment")
    goal_linked = (
        data.get("question_status") in {"settled", "conditional_advance"}
        or data.get("research_value") == "advances_question"
    )
    alignment = (
        _json_evidence(
            alignment_ref.get("report") if isinstance(alignment_ref, dict) else None,
            base_dir, "gold record goal alignment", errors,
        ) if goal_linked else None
    )
    if target is None or kernel is None or (goal_linked and alignment is None):
        return errors
    target_hash = target.get("target_signature_hash")
    target_signature = target.get("target_signature")
    if target.get("plan_statement_id") != statement_id:
        return [*errors, "GOLD_RECORD_INVALID: statement id is not bound by the target contract"]
    face_declarations = {
        face.get("lean_decl") for face in data.get("theorem_faces", [])
        if isinstance(face, dict) and face.get("covered") is True
    }
    matching_roots = [
        root for root in kernel.get("root_declarations", [])
        if isinstance(root, dict)
        and root.get("signature_hash") == target_hash
        and root.get("name") in face_declarations
    ] if isinstance(kernel.get("root_declarations"), list) else []
    if len(matching_roots) != 1:
        return [*errors, "GOLD_RECORD_AMBIGUOUS: expected exactly one audited target root"]
    root = matching_roots[0]
    lean_path, lean_payload = _evidence_path(
        root.get("lean_file"), base_dir, "gold record root Lean file", errors,
    )
    if lean_path is None or lean_payload is None:
        return errors

    component_boundaries: set[str] = set()
    for assumption in data.get("assumptions", []):
        if not isinstance(assumption, dict) or assumption.get("kind") != "boundary":
            continue
        closure = _json_evidence(
            assumption.get("source_closure"), base_dir,
            f"gold record boundary {assumption.get('id')} closure", errors,
        )
        if closure is None:
            continue
        face = next((
            item for item in closure.get("faces", [])
            if isinstance(item, dict) and item.get("id") == assumption.get("id")
        ), None)
        if not isinstance(face, dict) or not isinstance(face.get("boundary_ids"), list):
            errors.append("GOLD_RECORD_INVALID: boundary component census is unavailable")
        else:
            component_boundaries.update(face["boundary_ids"])
    if errors:
        return errors
    evidence_snapshot = _evidence_snapshot(data, base_dir)
    if evidence_snapshot is None:
        return ["GOLD_RECORD_STALE: transitive evidence closure changed before recording"]
    evidence_files, evidence_set_hash = evidence_snapshot

    try:
        from offline_cli import _plan_lock
        from plan_store.offline_store import OfflinePlanGraph
    except ImportError as exc:
        return [f"GOLD_RECORD_FAILED: offline plan backend is unavailable: {exc}"]

    plan_data = plan_data.resolve()
    lock = _plan_lock(plan_data)
    graph = None
    lock.acquire()
    try:
        graph = OfflinePlanGraph(plan_data)
        node = graph.get(statement_id)
        if node is None:
            errors.append(f"GOLD_RECORD_INVALID: unknown statement {statement_id!r}")
        elif node.get("type") in {"Summary", "Note"} or node.get("kind") == "summary":
            errors.append("GOLD_RECORD_INVALID: meta nodes cannot receive Gold")
        elif node.get("status") != "completed" or node.get("proof_status") != "completed":
            errors.append("GOLD_RECORD_INVALID: target node is not fully completed")
        elif node.get("status") == "completed_axiom":
            errors.append("GOLD_RECORD_INVALID: completed_axiom nodes cannot receive Gold")
        else:
            node_lean = node.get("lean_path")
            if not _nonempty_string(node_lean):
                errors.append("GOLD_RECORD_INVALID: target node has no Lean path")
            else:
                candidate = Path(node_lean)
                candidate = candidate.resolve() if candidate.is_absolute() else (base_dir / candidate).resolve()
                if candidate != lean_path.resolve():
                    errors.append("GOLD_RECORD_INVALID: plan node Lean path is not the audited target root")
            if node.get("anchor") != target_signature or hashlib.sha256(
                str(node.get("anchor") or "").encode()
            ).hexdigest() != target_hash:
                errors.append("GOLD_RECORD_INVALID: plan node anchor is not the exact frozen target signature")
            for field in ("result_scope", "question_status", "research_value"):
                if node.get(field) != data.get(field):
                    errors.append(f"GOLD_RECORD_INVALID: plan node {field} disagrees with manifest")
            if goal_linked and isinstance(alignment, dict):
                expected_alignment = {
                    "goal_id": alignment.get("goal_id"),
                    "goal_role": alignment.get("classification"),
                    "directionality": alignment.get("directionality"),
                    "consumer_path": alignment.get("consumer_path"),
                }
                for field, expected in expected_alignment.items():
                    if node.get(field) != expected:
                        errors.append(f"GOLD_RECORD_INVALID: plan node {field} disagrees with goal audit")
                if not isinstance(node.get("consumer_path"), list) or not node["consumer_path"] or node["consumer_path"][0] != statement_id:
                    errors.append("GOLD_RECORD_INVALID: plan statement is not the audited consumer-path root")
            if set(node.get("boundary_axiom_ids") or []) != component_boundaries:
                errors.append("GOLD_RECORD_INVALID: plan boundary census disagrees with source closure")
            if node.get("open_assumptions") != []:
                errors.append("GOLD_RECORD_INVALID: plan node still has open non-boundary assumptions")
            if node.get("evidence_closure_sha256") != manifest_hash:
                errors.append("GOLD_RECORD_INVALID: plan node does not bind the audited manifest hash")

        try:
            current_manifest = manifest_path.read_bytes()
            current_lean = lean_path.read_bytes()
        except OSError as exc:
            errors.append(f"GOLD_RECORD_STALE: evidence changed or disappeared: {exc}")
        else:
            if current_manifest != manifest_bytes:
                errors.append("GOLD_RECORD_STALE: manifest changed before commit")
            if hashlib.sha256(current_lean).hexdigest() != root.get("lean_file", {}).get("sha256"):
                errors.append("GOLD_RECORD_STALE: target Lean source changed before commit")
        if not errors:
            errors.extend(audit_manifest(data, base_dir, kernel_runtime_verified=True))
        if not errors and _evidence_snapshot(data, base_dir) != evidence_snapshot:
            errors.append("GOLD_RECORD_STALE: transitive evidence closure changed before commit")
        if not errors and graph is not None:
            receipt = {
                "schema_version": 2,
                "status": "passed",
                "auditor": "merlean-research-grade",
                "auditor_version": 2,
                "manifest_path": str(manifest_path),
                "manifest_sha256": manifest_hash,
                "lean_file_sha256": root.get("lean_file", {}).get("sha256"),
                "evidence_files": evidence_files,
                "evidence_set_sha256": evidence_set_hash,
                "target_signature_sha256": target_hash,
                "root_declaration": root.get("name"),
                "plan_statement_id": statement_id,
                "plan_data_path": str(plan_data),
            }
            graph._record_audited_gold(statement_id, receipt)
            graph.close()
            graph = None
    except (OSError, ValueError, KeyError, TimeoutError) as exc:
        errors.append(f"GOLD_RECORD_FAILED: {exc}")
    finally:
        try:
            if graph is not None:
                graph.close()
        finally:
            lock.release()
    return errors
