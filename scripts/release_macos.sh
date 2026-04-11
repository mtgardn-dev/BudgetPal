#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUILD_SCRIPT="${SCRIPT_DIR}/app_build.sh"
DMG_SCRIPT="${SCRIPT_DIR}/app_make_dmg.sh"

if [[ ! -x "$BUILD_SCRIPT" ]]; then
  echo "[release:ERROR] Build script not found or not executable: $BUILD_SCRIPT"
  exit 1
fi
if [[ ! -x "$DMG_SCRIPT" ]]; then
  echo "[release:ERROR] DMG script not found or not executable: $DMG_SCRIPT"
  exit 1
fi

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  read -r -p "Enter release version (e.g. v0.1.0): " VERSION
fi

# Trim leading/trailing whitespace
VERSION="$(printf '%s' "$VERSION" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [[ -z "$VERSION" ]]; then
  echo "[release:ERROR] No version provided. Aborting."
  exit 1
fi

echo "[release] Project root: $PROJECT_ROOT"
echo "[release] Version: $VERSION"

echo "[release] Running app build..."
"$BUILD_SCRIPT" "$VERSION"

echo "[release] Running DMG packaging..."
"$DMG_SCRIPT" "$VERSION"

echo "[release] ✅ Done"
echo "[release] App: $PROJECT_ROOT/dist/BudgetPal.app"
echo "[release] DMG: $PROJECT_ROOT/dist/BudgetPal-${VERSION}-macOS.dmg"
