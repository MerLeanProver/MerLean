#!/usr/bin/env bash
# init-merlean — one-command setup for the Codex MerLEAN plugin.
# skills/ and src/ are tracked in the plugin, so nothing is mirrored: this script
# only prepares the RUNTIME — the shared .venv, the root .mcp.json, the .env key file, and the
# root Lean + Mathlib workspace. Cross-platform (Linux/macOS, and Windows via Git Bash).
#
#   full setup:            bash skills/init-merlean/scripts/setup.sh
#   with a key:            bash skills/init-merlean/scripts/setup.sh --openai-key sk-...
#   skip the slow parts:   bash skills/init-merlean/scripts/setup.sh --skip-mathlib
#
# Non-interactive by design (safe to run from a Codex skill). Re-running is idempotent.
set -euo pipefail

SKIP_VENV=0 ; SKIP_MATHLIB=0 ; OPENAI_KEY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --openai-key)   OPENAI_KEY="$2"; shift 2 ;;
    --skip-venv)    SKIP_VENV=1; shift ;;
    --skip-mathlib) SKIP_MATHLIB=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_ROOT/../.." && pwd)"
TPL="$SKILL_ROOT/templates"
ROOT_ENV="$REPO_ROOT/.env"
VENV_DIR="$REPO_ROOT/.venv"
VENV_PY="$VENV_DIR/bin/python"
ok()   { printf '  [ok] %s\n' "$1"; }
warn() { printf '  [!!] %s\n' "$1"; }

echo "MerLEAN Codex init  ->  $REPO_ROOT"

# --- 1. shared venv --------------------------------------------------------------------
resolve_venv_py() {
  if   [ -x "$VENV_DIR/bin/python" ];         then VENV_PY="$VENV_DIR/bin/python"
  elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then VENV_PY="$VENV_DIR/Scripts/python.exe"
  else return 1; fi
}
find_host_python() {  # print a usable python3 (>=3.9) interpreter path, or nothing
  for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 1)' >/dev/null 2>&1 \
      && { command -v "$c"; return 0; }
  done
  return 1
}
ensure_pip() {  # guarantee $VENV_PY has a working pip; nonzero if impossible
  "$VENV_PY" -m pip --version >/dev/null 2>&1 && return 0
  if "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1; then
    "$VENV_PY" -m pip --version >/dev/null 2>&1 && return 0
  fi
  local getpip="$VENV_DIR/.get-pip.py" rc=1   # last resort: bootstrap pip from pypa
  if command -v curl >/dev/null 2>&1; then
    curl -LsS https://bootstrap.pypa.io/get-pip.py -o "$getpip" 2>/dev/null || return 1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$getpip" https://bootstrap.pypa.io/get-pip.py 2>/dev/null || return 1
  else
    return 1
  fi
  "$VENV_PY" "$getpip" >/dev/null 2>&1 && rc=0 || rc=1
  rm -f "$getpip"
  [ "$rc" = 0 ] && "$VENV_PY" -m pip --version >/dev/null 2>&1
}
build_venv_with_python() {  # $1=host python: create venv if absent, ensure pip, install reqs
  local pyexe="$1"
  if ! resolve_venv_py; then
    "$pyexe" -m venv "$VENV_DIR" 2>/dev/null || "$pyexe" -m venv --without-pip "$VENV_DIR" || return 1
  fi
  resolve_venv_py || return 1
  if ! ensure_pip; then        # existing venv may be half-built (e.g. no pip): rebuild once
    rm -rf "$VENV_DIR"
    "$pyexe" -m venv --without-pip "$VENV_DIR" || return 1
    resolve_venv_py || return 1
    ensure_pip || return 1
  fi
  "$VENV_PY" -m pip install --upgrade pip --quiet
  "$VENV_PY" -m pip install -r "$REPO_ROOT/src/requirements.txt"   # pywin32 is gated by a platform marker
}
build_venv_with_uv() {  # uv provisions a python if none exists and installs without system pip
  command -v uv >/dev/null 2>&1 || return 1
  uv venv --python 3.12 "$VENV_DIR" >/dev/null 2>&1 || uv venv "$VENV_DIR" || return 1
  resolve_venv_py || return 1
  uv pip install --python "$VENV_PY" -r "$REPO_ROOT/src/requirements.txt"
}
if [ "$SKIP_VENV" = 1 ]; then
  echo "[1/4] skipping venv build (--skip-venv)"
  resolve_venv_py || true
else
  echo "[1/4] building shared venv ..."
  HOST_PY="$(find_host_python || true)"
  if [ -n "$HOST_PY" ] && build_venv_with_python "$HOST_PY"; then
    ok "venv ready: $VENV_PY"
  elif build_venv_with_uv; then
    ok "venv ready via uv: $VENV_PY"
  else
    echo "Could not build the Python venv." >&2
    echo "Install Python 3.9+ (incl. its venv module) or 'uv' (https://astral.sh/uv), then re-run." >&2
    exit 1
  fi
fi

# --- 2. .env / OpenAI key --------------------------------------------------------------
echo "[2/4] OpenAI key ..."
env_openai_key() {
  [ -f "$1" ] || return 1
  grep -Eq '^[[:space:]]*OPENAI_API_KEY[[:space:]]*=[[:space:]]*"?sk-' "$1"
}
if [ -n "$OPENAI_KEY" ]; then
  printf '# Mem0-g environment - OpenAI API key (written by init_merlean).\nOPENAI_API_KEY=%s\n' "$OPENAI_KEY" > "$ROOT_ENV"
  ok "wrote .env with the provided OPENAI_API_KEY"
elif env_openai_key "$ROOT_ENV"; then
  ok ".env already has an OPENAI_API_KEY - preserved"
elif [ -n "${OPENAI_API_KEY:-}" ]; then
  ok "OPENAI_API_KEY found in the environment (no .env needed)"
else
  [ -f "$ROOT_ENV" ] || cp -f "$TPL/.env.example" "$ROOT_ENV"
  warn "no key found - .env is a template; add OPENAI_API_KEY before running plan-graph commands"
fi

# --- 3. root config + Lean workspace ---------------------------------------------------
echo "[3/4] root config + Lean workspace ..."
if resolve_venv_py; then
  if [ ! -e "$REPO_ROOT/.mcp.json" ]; then
    cp -f "$TPL/mcp.json" "$REPO_ROOT/.mcp.json"
    ok ".mcp.json created (portable wrapper launches lean-lsp from the venv)"
  else
    ok ".mcp.json preserved"
  fi
else
  warn "no venv python - skipped .mcp.json generation"
fi
for name in lean-toolchain lakefile.toml MerLeanExperiment.lean; do
  if [ ! -e "$REPO_ROOT/$name" ]; then
    cp -f "$TPL/$name" "$REPO_ROOT/$name"
    ok "created $name"
  else
    ok "$name preserved"
  fi
done
if [ "$SKIP_MATHLIB" = 1 ]; then
  echo "  skipping Mathlib/Lake setup (--skip-mathlib)"
elif ! command -v lake >/dev/null 2>&1; then
  warn "lake not found - install Lean via elan (https://leanprover-community.github.io), then re-run"
else
  (
    cd "$REPO_ROOT"
    lake update
    if [ -f ".lake/packages/mathlib/lean-toolchain" ]; then
      mathlib_tc="$(tr -d '\r\n' < .lake/packages/mathlib/lean-toolchain)"
      root_tc=""
      [ -f lean-toolchain ] && root_tc="$(tr -d '\r\n' < lean-toolchain)"
      if [ -n "$mathlib_tc" ] && [ "$mathlib_tc" != "$root_tc" ]; then
        cp -f .lake/packages/mathlib/lean-toolchain lean-toolchain
        ok "synced lean-toolchain to Mathlib ($mathlib_tc)"
        lake update
      fi
    fi
    lake exe cache get
    lake build
  ) || { echo "Lean setup failed. Check lake/elan output above." >&2; exit 1; }
  ok "Lean workspace builds with Mathlib"
fi

# --- 4. checks ---------------------------------------------------------------------------
echo "[4/4] checks:"
if [ -x "$VENV_PY" ] && "$VENV_PY" -c "import lean_lsp_mcp" >/dev/null 2>&1; then
  ok "lean-lsp-mcp runnable from venv (lean-lsp MCP)"
else
  warn "lean-lsp-mcp not in venv - rebuild the venv (it is pinned in src/requirements.txt)"
fi
command -v lake >/dev/null 2>&1 && ok "lake on PATH (Lean builds runnable)" || warn "lake not found - install elan/Lean"
if [ -x "$VENV_PY" ]; then
  ( cd "$REPO_ROOT" && "$VENV_PY" -c "import sys; sys.path.insert(0, 'src'); import plan_store; print('  [ok] plan_store import OK')" ) \
    || warn "plan_store failed to import - check pip output above"
fi

echo ""
echo "Done. Verify:  $REPO_ROOT/scripts/merlean --data <DATA_DIR> status"
