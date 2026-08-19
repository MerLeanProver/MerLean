#!/usr/bin/env bash
# Build the shared repo-root .venv used by the plan-graph / plan-search / formalize / prove skills.
# Creates <repo>/.venv from .claude/requirements.txt and checks an OpenAI key is reachable at
# <repo>/.env or in the process environment. Cross-platform (Linux/macOS, and Windows via Git Bash).
#
#   Run from anywhere:  bash .claude/bootstrap.sh
set -euo pipefail

CLAUDE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CLAUDE_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
REQ="$CLAUDE_DIR/requirements.txt"

resolve_venv_py() {  # set VENV_PY to the venv interpreter (POSIX bin/ or Windows Scripts/), or fail
  if   [ -x "$VENV_DIR/bin/python" ];         then VENV_PY="$VENV_DIR/bin/python"
  elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then VENV_PY="$VENV_DIR/Scripts/python.exe"
  else return 1; fi
}

# --- 1. locate a Python interpreter to build the venv ---
PYEXE=""
for c in python3.14 python3.13 python3.12 python3.11 python3 python; do
  command -v "$c" >/dev/null 2>&1 && { PYEXE="$c"; break; }
done
[ -z "$PYEXE" ] && { echo "No python found. Install Python 3.11+ (3.14 preferred) on PATH." >&2; exit 1; }
echo "Using Python: $PYEXE"

# --- 2. create the venv (idempotent) and install pinned deps ---
resolve_venv_py || { echo "Creating venv at $VENV_DIR ..."; "$PYEXE" -m venv "$VENV_DIR"; }
resolve_venv_py || { echo "venv python not found under $VENV_DIR" >&2; exit 1; }
echo "Installing $REQ ..."
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -r "$REQ"   # pywin32 is gated by a platform marker

# --- 3. ensure an OpenAI key is reachable at repo-root .env ---
ROOT_ENV="$REPO_ROOT/.env"
if [ ! -f "$ROOT_ENV" ]; then
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "OPENAI_API_KEY is set in the environment; no .env needed."
  else
    echo "No key found. Create .env with OPENAI_API_KEY=... or set the env var." >&2
  fi
fi

echo ""
echo "Done. The shared environment is ready under $VENV_DIR."
echo "Verify:  $VENV_PY .claude/skills/plan-graph/cli.py --data <DATA_DIR> status"
