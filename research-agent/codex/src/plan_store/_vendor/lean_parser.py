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

    def build_registry(self, library_path: Path) -> None:
        """Build a registry of all declarations in the library."""
        self.library_name = library_path.name
        self.registry = {}
        self.file_to_declarations = {}
        self.file_to_label = {}

        for lean_path in sorted(library_path.rglob("*.lean")):
            if ".lake" in str(lean_path):
                continue
            try:
                content = lean_path.read_text(encoding='utf-8')
                filename = lean_path.name

                file_label = self._filename_to_label(filename)
                self.file_to_label[filename] = file_label

                declarations = self._extract_declarations(content)
                self.file_to_declarations[filename] = [(d[0], d[1]) for d in declarations]

                for decl_name, decl_type, namespace in declarations:
                    full_key = f"{namespace}.{decl_name}" if namespace else decl_name
                    self.registry[full_key] = {
                        'file': filename,
                        'path': lean_path,
                        'label': file_label,
                        'type': decl_type,
                        'namespace': namespace,
                        'decl_label': self._make_decl_label(decl_name, decl_type, namespace),
                        'short_name': decl_name,
                    }
            except Exception as e:
                print(f"Warning: Could not analyze {lean_path}: {e}")

    def _extract_declarations(self, content: str) -> list:
        """Extract all declaration names, types, and enclosing namespaces."""
        declarations = []
        content_clean = self._remove_comments(content, for_dependency_search=True)

        namespace_at_pos = {}
        namespace_stack = []
        lines = content_clean.split('\n')
        char_pos = 0

        for line in lines:
            ns_match = re.match(r'\s*namespace\s+(\w+)', line)
            if ns_match:
                namespace_stack.append(ns_match.group(1))

            end_match = re.match(r'\s*end\s+(\w+)', line)
            if end_match and namespace_stack:
                end_name = end_match.group(1)
                if namespace_stack and namespace_stack[-1] == end_name:
                    namespace_stack.pop()

            current_ns = ".".join(namespace_stack) if namespace_stack else None
            for i in range(len(line) + 1):
                namespace_at_pos[char_pos + i] = current_ns
            char_pos += len(line) + 1

        keywords = [
            'def', 'theorem', 'lemma', 'structure', 'inductive', 'class',
            'instance', 'axiom', 'abbrev', 'proposition', 'corollary'
        ]

        for keyword in keywords:
            pattern = rf'''
                ^\s*                                        # Start of line
                (?:(?:noncomputable|private|protected|partial)\s+)*  # Optional modifiers
                {keyword}\s+                                # Keyword
                ([A-Za-z_][A-Za-z0-9_']*)                   # Declaration name
                \b
            '''
            for match in re.finditer(pattern, content_clean, re.VERBOSE | re.MULTILINE):
                decl_name = match.group(1)
                if decl_name not in ['_', 'this', 'that', 'h', 'H', 'hs', 'ih']:
                    pos = match.start()
                    namespace = namespace_at_pos.get(pos, None)
                    declarations.append((decl_name, keyword, namespace))

        return declarations

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
            decl_match = re.search(rf'\b(def|theorem|lemma|structure)\s+{re.escape(decl_name)}\b', content)
            if not decl_match:
                return None
            decl_pos = decl_match.start()
            namespace_stack = []
            for m in re.finditer(r'\b(namespace|end)\s+(\w+)', content[:decl_pos]):
                keyword = m.group(1)
                name = m.group(2)
                if keyword == 'namespace':
                    namespace_stack.append(name)
                elif keyword == 'end' and namespace_stack and namespace_stack[-1] == name:
                    namespace_stack.pop()
            return namespace_stack[-1] if namespace_stack else None

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
