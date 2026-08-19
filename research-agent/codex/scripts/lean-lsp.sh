#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -x "$PLUGIN_ROOT/.venv/bin/python" ]; then
  exec "$PLUGIN_ROOT/.venv/bin/python" -m lean_lsp_mcp
fi
if [ -x "$PLUGIN_ROOT/.venv/Scripts/python.exe" ]; then
  exec "$PLUGIN_ROOT/.venv/Scripts/python.exe" -m lean_lsp_mcp
fi

echo "MerLEAN runtime missing; run the init-merlean skill first." >&2
exit 1
