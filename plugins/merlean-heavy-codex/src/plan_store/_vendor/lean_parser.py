"""Lean file parser for extracting definitions, theorems, and proofs.

Verbatim from src/autoinformalization/lean_parser.py; only the model import is
repointed to the vendored copy.
"""

import re
from pathlib import Path
from typing import Optional

from .lean_models import LeanItem, LeanItemType, LeanFile, parse_statement_filename


# Rem/Prelim map to 'def' so they render as square boxes in the blueprint graph.
_LABEL_PREFIX_MAP = {
    "Def": "def", "Thm": "thm", "Lem": "lem",
    "Prop": "prop", "Cor": "cor",
    "Rem": "def", "Prelim": "def",
}


def filename_to_label(filename: str, library_name: str = "") -> tuple[str, str]:
    """Convert a filename to a label (without library prefix). Returns (label, short_name)."""
    stem = Path(filename).stem
    parsed = parse_statement_filename(stem)

    if parsed.is_recognized and parsed.stmt_num:
        label_prefix = _LABEL_PREFIX_MAP.get(parsed.type_prefix, "item")
        return (f"{label_prefix}:{parsed.stmt_name}", parsed.stmt_name)

    return (f"item:{stem}", stem)


class LeanParser:
    """Parser for Lean 4 files."""

    DECLARATION_KEYWORDS = {
        "def": LeanItemType.DEFINITION,
        "theorem": LeanItemType.THEOREM,
        "lemma": LeanItemType.LEMMA,
        "proposition": LeanItemType.PROPOSITION,
        "corollary": LeanItemType.COROLLARY,
        "structure": LeanItemType.STRUCTURE,
        "inductive": LeanItemType.INDUCTIVE,
        "class": LeanItemType.CLASS,
        "instance": LeanItemType.INSTANCE,
        "axiom": LeanItemType.AXIOM,
        "example": LeanItemType.EXAMPLE,
        "notation": LeanItemType.NOTATION,
        "abbrev": LeanItemType.ABBREV,
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def parse_file(self, file_path: Path) -> LeanFile:
        """Parse a Lean file and extract all declarations."""
        content = file_path.read_text(encoding='utf-8')

        try:
            rel_path = file_path.relative_to(self.project_root)
            module_name = str(rel_path.with_suffix('')).replace('\\', '.').replace('/', '.')
        except ValueError:
            module_name = file_path.stem

        lean_file = LeanFile(
            path=file_path,
            module_name=module_name,
            imports=self._extract_imports(content),
            module_docstring=self._extract_module_docstring(content),
            items=self._extract_items(content, file_path),
        )

        return lean_file

    def _extract_imports(self, content: str) -> list[str]:
        """Extract import statements."""
        imports = []
        for match in re.finditer(r'^import\s+(\S+)', content, re.MULTILINE):
            imports.append(match.group(1))
        return imports

    def _extract_module_docstring(self, content: str) -> Optional[str]:
        """Extract the module-level docstring (/-! ... -/)."""
        match = re.search(r'/\-\!(.+?)\-/', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _extract_items(self, content: str, file_path: Path) -> list[LeanItem]:
        """Extract all declarations from the file."""
        items = []

        docstring_placeholder = {}
        docstring_pattern = re.compile(r'/\-\-(.+?)\-/', re.DOTALL)
        docstring_count = [0]

        def replace_docstring(m):
            key = f"__DOCSTRING_{docstring_count[0]}__"
            docstring_placeholder[key] = m.group(1).strip()
            docstring_count[0] += 1
            return key

        content_with_placeholders = docstring_pattern.sub(replace_docstring, content)
        content_no_comments = re.sub(r'--.*$', '', content_with_placeholders, flags=re.MULTILINE)
        content_no_comments = re.sub(r'/\-(?!\!)(.+?)\-/', '', content_no_comments, flags=re.DOTALL)

        for keyword, item_type in self.DECLARATION_KEYWORDS.items():
            pattern = rf'''
                (?:@\[([^\]]*)\]\s*)?  # Optional attributes
                (?:(?:noncomputable|private|protected|partial)\s+)*  # Optional modifiers
                {keyword}\s+          # Keyword
                (\w+)                 # Name
                ([^:]*?)              # Parameters (before colon)
                :\s*                  # Colon
                ([^:=]+?)             # Type signature (before := or where)
                (?:
                    :=\s*(.+?)        # Definition body after :=
                    |where\s+(.+?)    # or struct/class body after where
                    |$                # or end of match
                )
                (?=\n\s*(?:@\[|def\s|theorem\s|lemma\s|structure\s|inductive\s|class\s|instance\s|axiom\s|example\s|notation\s|abbrev\s|proposition\s|corollary\s|section\s|namespace\s|end\s|variable\s|open\s|/-|$))
            '''

            for match in re.finditer(pattern, content_no_comments, re.VERBOSE | re.DOTALL):
                attrs = match.group(1)
                name = match.group(2)
                params = match.group(3).strip() if match.group(3) else ""
                type_sig = match.group(4).strip() if match.group(4) else ""
                body1 = match.group(5)
                body2 = match.group(6)

                body = (body1 or body2 or "").strip()

                signature = f"{params} : {type_sig}".strip()
                if signature.startswith(":"):
                    signature = signature[1:].strip()

                docstring = None
                for key, doc in docstring_placeholder.items():
                    if key in content_no_comments[:match.start()]:
                        docstring = doc

                attributes = []
                if attrs:
                    attributes = [a.strip() for a in attrs.split(',')]

                item = LeanItem(
                    name=name,
                    item_type=item_type,
                    signature=signature,
                    body=body if body else None,
                    docstring=docstring,
                    attributes=attributes,
                    source_file=file_path,
                    line_number=content[:match.start()].count('\n') + 1,
                )
                items.append(item)

        items.sort(key=lambda x: x.line_number)
        return items

    def parse_library(self, library_path: Path) -> list[LeanFile]:
        """Parse all Lean files in a library directory."""
        lean_files = []
        for lean_path in sorted(library_path.rglob("*.lean")):
            if ".lake" in str(lean_path):
                continue
            try:
                lean_file = self.parse_file(lean_path)
                lean_files.append(lean_file)
            except Exception as e:
                print(f"Warning: Could not parse {lean_path}: {e}")
        return lean_files


# =============================================================================
# Dependency Analysis
# =============================================================================

class DependencyAnalyzer:
    """Analyzes dependencies between Lean files by searching for declaration usages."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.library_name: str = ""
        self.registry: dict[str, dict] = {}
        self.file_to_declarations: dict[str, list] = {}
        self.file_to_label: dict[str, str] = {}
        self.file_to_declaration_records: dict[str, list[dict]] = {}

    def build_registry(self, library_path: Path) -> None:
        """Build a registry of all declarations in the library."""
        self.library_name = library_path.name
        self.registry = {}
        self.file_to_declarations = {}
        self.file_to_label = {}
        self.file_to_declaration_records = {}

        for lean_path in sorted(library_path.rglob("*.lean")):
            if ".lake" in str(lean_path):
                continue
            try:
                content = lean_path.read_text(encoding='utf-8')
                filename = lean_path.name

                file_label = self._filename_to_label(filename)
                self.file_to_label[filename] = file_label

                records = self._extract_declaration_records(content)
                self.file_to_declaration_records[filename] = records
                self.file_to_declarations[filename] = [(r["name"], r["type"]) for r in records]

                for record in records:
                    decl_name, decl_type, namespace = record["name"], record["type"], record["namespace"]
                    full_key = record["full_name"]
                    self.registry[full_key] = {
                        'file': filename,
                        'path': lean_path,
                        'label': file_label,
                        'type': decl_type,
                        'namespace': namespace,
                        'decl_label': self._make_decl_label(decl_name, decl_type, namespace),
                        'short_name': decl_name,
                    }
            except ValueError as e:
                # Never turn an unresolved scope into an empty, apparently clean census.
                raise ValueError(f"Could not identify declarations in {lean_path}: {e}") from e
            except Exception as e:
                print(f"Warning: Could not analyze {lean_path}: {e}")

    @staticmethod
    def _mask_noncode(content: str) -> str:
        """Mask comments/strings while preserving offsets and physical line numbers."""
        chars = list(content)
        i, depth, in_string = 0, 0, False
        while i < len(content):
            if depth:
                if content.startswith("/-", i):
                    chars[i:i + 2] = "  "
                    depth += 1
                    i += 2
                elif content.startswith("-/", i):
                    chars[i:i + 2] = "  "
                    depth -= 1
                    i += 2
                else:
                    if content[i] != "\n":
                        chars[i] = " "
                    i += 1
            elif in_string:
                if content[i] == "\\" and i + 1 < len(content):
                    chars[i] = " "
                    if content[i + 1] != "\n":
                        chars[i + 1] = " "
                    i += 2
                else:
                    if content[i] == '"':
                        in_string = False
                    if content[i] != "\n":
                        chars[i] = " "
                    i += 1
            elif content.startswith("/-", i):
                chars[i:i + 2] = "  "
                depth = 1
                i += 2
            elif content.startswith("--", i):
                while i < len(content) and content[i] != "\n":
                    chars[i] = " "
                    i += 1
            elif content[i] == '"':
                chars[i] = " "
                in_string = True
                i += 1
            elif content[i] == "«":
                # A quoted identifier is code, even if it contains comment markers.
                close = content.find("»", i + 1)
                i = close + 1 if close >= 0 else len(content)
            else:
                i += 1
        return "".join(chars)

    def _extract_declaration_records(self, content: str) -> list[dict]:
        """Extract occurrence identities; this is a lexical census, not elaboration.

        Keep scope and location on each occurrence, rather than recovering identity
        from the project registry (where a true duplicate may overwrite a key).
        """
        ident = r"(?:«[^»\n]+»|[^\W\d][\w']*)"
        name = rf"{ident}(?:\.{ident})*"
        scope_re = re.compile(rf"^\s*(?:noncomputable\s+)?(namespace|section)\b(?:\s+({name}))?")
        end_re = re.compile(rf"^\s*end\b(?:\s+({name}))?\s*$")
        decl_re = re.compile(
            rf"^\s*(?P<modifiers>(?:(?:noncomputable|private|protected|partial)\s+)*)"
            rf"(?P<kind>def|theorem|lemma|structure|inductive|class|instance|axiom|abbrev|proposition|corollary)"
            rf"\s+(?P<name>{name})(?![\w'])"
        )
        # Section frames participate in end matching but not declaration names.
        frames: list[tuple[str, Optional[str]]] = []
        records = []
        offset = 0
        for line_number, line in enumerate(self._mask_noncode(content).splitlines(keepends=True), 1):
            scope = scope_re.match(line)
            ending = end_re.match(line)
            if scope:
                kind, scope_name = scope.groups()
                if kind == "namespace" and scope_name is None:
                    raise ValueError(f"Missing namespace name at line {line_number}")
                frames.append((kind, scope_name))
            elif ending:
                if frames:
                    end_name = ending.group(1)
                    if end_name is not None and end_name != frames[-1][1]:
                        raise ValueError(f"Mismatched scope end at line {line_number}: {end_name}")
                    frames.pop()
                elif ending.group(1) is not None:
                    raise ValueError(f"Unmatched scope end at line {line_number}")
            else:
                match = decl_re.match(line)
                if match:
                    source_name = match.group("name")
                    if source_name not in ["_", "this", "that", "h", "H", "hs", "ih"]:
                        namespace = ".".join(n for k, n in frames if k == "namespace" and n)
                        if source_name.startswith("_root_."):
                            full_name = source_name[len("_root_."):]
                        else:
                            full_name = f"{namespace}.{source_name}" if namespace else source_name
                        records.append({
                            "name": source_name,
                            "type": match.group("kind"),
                            "namespace": namespace or None,
                            "full_name": full_name,
                            "line": line_number,
                            "position": offset + match.start("kind"),
                            "is_private": "private" in match.group("modifiers").split(),
                        })
            offset += len(line)
        return records

    def _extract_declarations(self, content: str) -> list:
        """Compatibility projection for declaration-level dependency consumers."""
        return [(r["name"], r["type"], r["namespace"])
                for r in self._extract_declaration_records(content)]

    def _remove_comments(self, content: str, for_dependency_search: bool = False) -> str:
        """Remove comments from Lean content."""
        if for_dependency_search:
            content = re.sub(r'/\-\!(.+?)\-/', '', content, flags=re.DOTALL)
            content = re.sub(r'/\-\-(.+?)\-\-/', '', content, flags=re.DOTALL)
            content = re.sub(r'/\-(.+?)\-/', '', content, flags=re.DOTALL)
            content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
            content = re.sub(r'"[^"]*"', '""', content)
        else:
            content = re.sub(r'/\-(?!\!)(?!\-)(.+?)\-/', '', content, flags=re.DOTALL)
            content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
        return content

    def _filename_to_label(self, filename: str) -> str:
        label, _ = filename_to_label(filename, library_name=self.library_name)
        return label

    def _make_decl_label(self, decl_name: str, decl_type: str, namespace: str = None) -> str:
        """Create a label for a specific declaration (without library prefix)."""
        parts = []
        if namespace:
            parts.append(namespace)
        parts.append(decl_name)
        fqn = ".".join(parts)

        prefix_map = {
            "def": "def", "theorem": "thm", "lemma": "lem",
            "structure": "def", "inductive": "def", "class": "def",
            "instance": "inst", "axiom": "thm", "abbrev": "def",
            "proposition": "prop", "corollary": "cor"
        }
        prefix = prefix_map.get(decl_type, "item")
        return f"{prefix}:{fqn}"

    def find_dependencies(self, file_path: Path, include_self: bool = False,
                          filter_by_imports: bool = True,
                          include_imports: bool = True) -> list[str]:
        """Find all dependencies of a file by searching for declaration usages."""
        if not self.registry:
            raise ValueError("Registry not built. Call build_registry() first.")

        content = file_path.read_text(encoding='utf-8')
        filename = file_path.name

        imported_modules = set()
        imported_files = set()
        for match in re.finditer(r'^import\s+(\S+)', content, re.MULTILINE):
            import_path = match.group(1)
            import_path = import_path.replace('«', '').replace('»', '')
            parts = import_path.split('.')
            if parts:
                imported_modules.add(import_path)
                for i in range(len(parts)):
                    imported_modules.add('.'.join(parts[i:]))
                file_stem = parts[-1].replace('«', '').replace('»', '')
                imported_files.add(file_stem)

        content_clean = self._remove_comments(content, for_dependency_search=True)

        self_declarations = set()
        if not include_self and filename in self.file_to_declarations:
            self_declarations = {d[0] for d in self.file_to_declarations[filename]}

        dependencies = set()

        for full_key, info in self.registry.items():
            if info['file'] == filename:
                continue

            short_name = info.get('short_name', full_key)

            if short_name in self_declarations:
                continue

            if filter_by_imports and imported_modules:
                decl_file = info['file']
                decl_stem = Path(decl_file).stem
                is_imported = any(decl_stem in mod for mod in imported_modules)
                if not is_imported:
                    continue

            if len(short_name) <= 2:
                continue

            pattern = rf'(?<![.\w]){re.escape(short_name)}\b'
            if re.search(pattern, content_clean):
                dependencies.add(info['decl_label'])

        if include_imports and imported_files:
            for imp_file_stem in imported_files:
                for reg_filename, label in self.file_to_label.items():
                    reg_stem = Path(reg_filename).stem
                    if reg_stem == imp_file_stem and reg_filename != filename:
                        dependencies.add(label)
                        break

        return sorted(dependencies)

    def find_declaration_dependencies(self, file_path: Path) -> dict:
        """Find dependencies at the declaration level (more granular)."""
        if not self.registry:
            raise ValueError("Registry not built. Call build_registry() first.")

        content = file_path.read_text(encoding='utf-8')
        filename = file_path.name

        if filename not in self.file_to_declarations:
            return {}

        declarations = self.file_to_declarations[filename]

        result = {}
        content_clean = self._remove_comments(content, for_dependency_search=True)

        namespace_to_struct = {}
        for full_key, info in self.registry.items():
            if info['type'] in ('structure', 'def', 'abbrev', 'class', 'inductive'):
                short_name = info.get('short_name', full_key)
                namespace_to_struct[short_name] = info['decl_label']

        def find_enclosing_namespace(content: str, decl_name: str) -> Optional[str]:
            matches = [r for r in self._extract_declaration_records(content)
                       if r["name"] == decl_name]
            # This legacy short-name API cannot disambiguate repeated occurrences.
            # Do not invent a scope by selecting the first one.
            return matches[0]["namespace"] if len(matches) == 1 else None

        for decl_name, decl_type in declarations:
            body = self._extract_declaration_body(content_clean, decl_name, decl_type)
            if not body:
                result[decl_name] = []
                continue

            LEAN_KEYWORDS = {
                'have', 'let', 'show', 'suffices', 'assume', 'this', 'that',
                'apply', 'exact', 'intro', 'intros', 'cases', 'induction',
                'simp', 'rfl', 'trivial', 'sorry', 'ring', 'omega', 'decide',
                'constructor', 'ext', 'funext', 'congr', 'subst', 'rw', 'rewrite',
                'calc', 'obtain', 'rcases', 'rintro', 'push_neg', 'contrapose',
                'by_contra', 'exfalso', 'absurd', 'native_decide',
                'zero', 'one', 'id', 'comp', 'map', 'pure', 'bind', 'seq',
                'add', 'mul', 'neg', 'sub', 'div', 'inv', 'pow', 'smul', 'vadd',
                'on', 'of', 'in', 'is', 'at', 'to', 'for', 'or', 'and', 'not',
                'eq', 'ne', 'lt', 'le', 'gt', 'ge', 'mk', 'val', 'get', 'set',
            }

            deps = set()
            for full_key, info in self.registry.items():
                short_name = info.get('short_name', full_key)
                if short_name == decl_name:
                    continue
                if short_name.lower() in LEAN_KEYWORDS or short_name in LEAN_KEYWORDS:
                    continue
                # Most registry names do not occur in this declaration body.  Avoid
                # compiling a regular expression for every absent name: on libraries
                # with thousands of declarations the old loop made visualization
                # effectively quadratic and could take minutes per plan node.
                if short_name not in body:
                    continue
                pattern = rf'(?<![.\w]){re.escape(short_name)}\b'
                if re.search(pattern, body):
                    deps.add(info['decl_label'])

            enclosing_ns = find_enclosing_namespace(content_clean, decl_name)
            if enclosing_ns and enclosing_ns in namespace_to_struct:
                ns_label = namespace_to_struct[enclosing_ns]
                this_full_key = f"{enclosing_ns}.{decl_name}" if enclosing_ns else decl_name
                decl_label = self.registry.get(this_full_key, {}).get('decl_label', '')
                if ns_label != decl_label:
                    deps.add(ns_label)

            result[decl_name] = sorted(deps)

        return result

    def _extract_declaration_body(self, content: str, decl_name: str, decl_type: str) -> Optional[str]:
        """Extract the body of a specific declaration."""
        stop_patterns = [
            r'def\s', r'theorem\s', r'lemma\s', r'structure\s', r'inductive\s',
            r'class\s', r'instance\s', r'axiom\s', r'abbrev\s', r'proposition\s',
            r'corollary\s', r'section\s', r'namespace\s', r'end\s', r'variable\s',
            r'open\s', r'set_option\s', r'@\[', r'/-!', r'\#check\s', r'\#eval\s',
            r'\#print\s', r'noncomputable\s+def', r'noncomputable\s+theorem',
            r'noncomputable\s+lemma', r'noncomputable\s+structure',
            r'noncomputable\s+instance', r'private\s+def', r'private\s+theorem',
            r'private\s+lemma', r'protected\s+def', r'protected\s+theorem',
            r'protected\s+lemma',
        ]
        stop_lookahead = '|'.join(stop_patterns)

        pattern = rf'''
            (?:(?:noncomputable|private|protected|partial)\s+)*
            {decl_type}\s+{re.escape(decl_name)}\b
            (.+?)
            (?=\n\s*(?:{stop_lookahead})|$)
        '''
        match = re.search(pattern, content, re.VERBOSE | re.DOTALL)
        if match:
            return match.group(1)
        return None

    def build_dependency_graph(self, library_path: Path) -> dict:
        """Build a complete file-label dependency graph for the entire library."""
        if not self.registry:
            self.build_registry(library_path)

        graph = {}
        for lean_path in sorted(library_path.rglob("*.lean")):
            if ".lake" in str(lean_path):
                continue
            filename = lean_path.name
            if filename not in self.file_to_label:
                continue
            label = self.file_to_label[filename]
            deps = self.find_dependencies(lean_path)
            graph[label] = deps
        return graph
