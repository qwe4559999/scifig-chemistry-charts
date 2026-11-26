#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  SciFigStudio Interactive Workbench (v2.1.0)"
echo "  Origin-free Declarative Chemistry Figure Studio"
echo "============================================================"

if command -v python3 >/dev/null 2>&1; then
  PYCMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYCMD="python"
else
  echo "[ERROR] Python 3.10+ not found in PATH." >&2
  exit 1
fi

echo "[1/2] Checking required Python packages..."
if ! "$PYCMD" -X utf8 -c "import matplotlib, numpy, scipy, pandas, PIL, pymupdf, openpyxl" >/dev/null 2>&1; then
  echo "[INFO] Installing missing dependencies from requirements.txt..."
  "$PYCMD" -m pip install -r requirements.txt
fi

export SCIFIG_ASSETS="$SCRIPT_DIR/assets"
export PYTHONUTF8=1

echo "[2/2] Starting Interactive Workbench..."
exec "$PYCMD" -X utf8 -m scifig workbench "$@"
