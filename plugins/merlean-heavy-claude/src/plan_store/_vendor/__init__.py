"""Verbatim copies of pure helpers from the predecessor plan store (read-only ref).

- models.py      : Statement, StatementType        (src/autoformalization/models.py)
- toposort.py    : topologically_sort_statements,
                   find_dependency_cycles           (src/autoformalization/scripts/statement_io.py)
- cone.py        : forward_dependency_cone           (src/autoformalization/scripts/compile_loop.py)
- lean_models.py : LeanItem/LeanFile/parse_statement_filename (src/autoinformalization/models.py)
- lean_parser.py : LeanParser, DependencyAnalyzer    (src/autoinformalization/lean_parser.py)
"""
