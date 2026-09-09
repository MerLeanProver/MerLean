"""Launcher for the plan_store CLI, runnable from anywhere:

    .venv/bin/python src/cli.py --data <DATA_DIR> <cmd> ...

Adds this directory to sys.path so the `plan_store` package (sibling) imports cleanly,
regardless of the current working directory. `PLAN_OFFLINE=1` selects the local JSON
backend (`offline_cli`) before any online plan_store module is imported.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if os.environ.get("PLAN_OFFLINE", "0") == "1":
    from offline_cli import main  # noqa: E402
else:
    from plan_store.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1:])
