#!/usr/bin/env bash
set -euo pipefail

# Build BudgetPal macOS app bundle with PyInstaller.
# Usage: ./scripts/app_build.sh [version]

APP_NAME="BudgetPal"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION_ARG="${1:-}"
BOOTSTRAP_DIR="$PROJECT_ROOT/bootstrap_data"
CONFIG_SRC="$PROJECT_ROOT/config"
PACKAGED_CONFIG_SRC="${PACKAGED_CONFIG_SRC:-$PROJECT_ROOT/config/budgetpal_config.example.json}"
IMAGES_SRC="$PROJECT_ROOT/images"
HELP_SRC="$PROJECT_ROOT/help"
ENTRYPOINT="$PROJECT_ROOT/core/main.py"
ICON_SRC="$PROJECT_ROOT/images/resources/budgetpal.icns"

echo "[build] PROJECT_ROOT = $PROJECT_ROOT"

if [[ ! -f "$ENTRYPOINT" ]]; then
  echo "[build:ERROR] Missing entrypoint: $ENTRYPOINT"
  exit 1
fi
if [[ ! -d "$CONFIG_SRC" ]]; then
  echo "[build:ERROR] Missing config directory: $CONFIG_SRC"
  exit 1
fi

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "[build:ERROR] Python interpreter not found."
  exit 1
fi

echo "[build] PYTHON_BIN = $PYTHON_BIN"

if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
  echo "[build] Installing PyInstaller into active environment..."
  "$PYTHON_BIN" -m pip install pyinstaller
fi

echo "[build] Cleaning dist/build/bootstrap_data..."
rm -rf dist build __pycache__ "$BOOTSTRAP_DIR"
mkdir -p "$BOOTSTRAP_DIR"

echo "[build] Copying config assets..."
cp -R "$CONFIG_SRC" "$BOOTSTRAP_DIR/config"
if [[ -f "$PACKAGED_CONFIG_SRC" ]]; then
  cp "$PACKAGED_CONFIG_SRC" "$BOOTSTRAP_DIR/config/budgetpal_config.json"
  echo "[build] Using packaged config template: $PACKAGED_CONFIG_SRC"
else
  echo "[build:WARN] Packaged config template not found; using config directory as-is."
fi

if [[ -d "$IMAGES_SRC" ]]; then
  cp -R "$IMAGES_SRC" "$BOOTSTRAP_DIR/images"
else
  echo "[build:WARN] Images directory not found: $IMAGES_SRC"
fi

if [[ -d "$HELP_SRC" ]]; then
  cp -R "$HELP_SRC" "$BOOTSTRAP_DIR/help"
else
  echo "[build:WARN] Help directory not found: $HELP_SRC"
fi

BUILD_TAG_RAW="$VERSION_ARG"
if [[ -z "$BUILD_TAG_RAW" ]]; then
  BUILD_TAG_RAW="${BUDGETPAL_BUILD_TAG:-}"
fi
if [[ -z "$BUILD_TAG_RAW" ]]; then
  BUILD_TAG_RAW="$(git -C "$PROJECT_ROOT" describe --tags --always --dirty 2>/dev/null || true)"
fi
BUILD_TAG="${BUILD_TAG_RAW%-dirty}"
if [[ -z "$BUILD_TAG" ]]; then
  BUILD_TAG="v0.0.0"
fi
BUILD_COMMIT="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
if [[ -z "$BUILD_COMMIT" ]]; then
  BUILD_COMMIT="unknown"
fi
BUILT_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$BOOTSTRAP_DIR/version.json" <<METADATA
{
  "build_tag": "$BUILD_TAG",
  "commit": "$BUILD_COMMIT",
  "built_at_utc": "$BUILT_AT_UTC"
}
METADATA

echo "[build] Wrote build metadata: $BOOTSTRAP_DIR/version.json ($BUILD_TAG)"

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --onedir
  --name "$APP_NAME"
  --add-data "bootstrap_data/config:config"
  --add-data "bootstrap_data/images:images"
  --add-data "bootstrap_data/help:help"
  --add-data "bootstrap_data/version.json:bootstrap_data"
)

if [[ -f "$ICON_SRC" ]]; then
  PYINSTALLER_ARGS+=(--icon "$ICON_SRC")
else
  echo "[build:WARN] Icon not found at $ICON_SRC; building without custom icon."
fi

echo "[build] Running PyInstaller..."
"$PYTHON_BIN" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ENTRYPOINT"

echo "[build] ✅ Build complete: dist/${APP_NAME}.app"
