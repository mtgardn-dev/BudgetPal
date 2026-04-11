#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ICON_SOURCE="${PROJECT_ROOT}/images/BudgetPal_Logo_Lg.png"
ICON_OUTPUT="${PROJECT_ROOT}/images/resources/budgetpal.icns"

if [[ ! -f "${ICON_SOURCE}" ]]; then
  echo "Icon source not found: ${ICON_SOURCE}"
  exit 1
fi

mkdir -p "$(dirname "${ICON_OUTPUT}")"

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Python interpreter not found. Cannot generate .icns icon."
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
from pathlib import Path

try:
    from PIL import Image
except Exception:
    print("Pillow is required to generate budgetpal.icns.")
    print("Install with: .venv/bin/python -m pip install pillow")
    raise SystemExit(1)

project_root = Path.cwd()
source = project_root / "images" / "BudgetPal_Logo_Lg.png"
output = project_root / "images" / "resources" / "budgetpal.icns"

if not source.exists():
    print(f"Icon source not found: {source}")
    raise SystemExit(1)

sizes = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]
img = Image.open(source).convert("RGBA")
img.save(output, format="ICNS", sizes=sizes)
print(f"Generated: {output}")
PY
