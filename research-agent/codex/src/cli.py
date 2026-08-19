"""Launcher for the plan_store CLI, runnable from anywhere:

    <PLUGIN_ROOT>/scripts/merlean --data <DATA_DIR> <cmd> ...

Adds this directory to sys.path so the `plan_store` package (sibling) imports cleanly,
regardless of the current working directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_store.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1:])
