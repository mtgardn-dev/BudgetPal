#!/usr/bin/env bash
# Build a drag-and-drop DMG for BudgetPal.
# Usage: ./scripts/app_make_dmg.sh [version]

set -euo pipefail

APP_NAME="BudgetPal"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
STAGE_DIR="$PROJECT_ROOT/build/dmg"
BOOTSTRAP_VERSION_JSON="$PROJECT_ROOT/bootstrap_data/version.json"
PREFER_CREATE_DMG="${PREFER_CREATE_DMG:-1}"
CREATE_DMG_TIMEOUT_SECONDS="${CREATE_DMG_TIMEOUT_SECONDS:-180}"

resolve_version() {
  local arg_version="${1:-}"
  if [[ -n "$arg_version" ]]; then
    echo "$arg_version"
    return 0
  fi

  if [[ -f "$BOOTSTRAP_VERSION_JSON" ]] && command -v /usr/bin/python3 >/dev/null 2>&1; then
    local from_json
    from_json="$(/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
path = Path('bootstrap_data/version.json')
try:
    payload = json.loads(path.read_text(encoding='utf-8'))
except Exception:
    print('')
else:
    print(str(payload.get('build_tag') or '').strip().removesuffix('-dirty'))
PY
)"
    if [[ -n "$from_json" ]]; then
      echo "$from_json"
      return 0
    fi
  fi

  local from_git
  from_git="$(git -C "$PROJECT_ROOT" describe --tags --abbrev=0 2>/dev/null || true)"
  if [[ -n "$from_git" ]]; then
    echo "${from_git%-dirty}"
    return 0
  fi
  from_git="$(git -C "$PROJECT_ROOT" describe --tags --always 2>/dev/null || true)"
  if [[ -n "$from_git" ]]; then
    echo "${from_git%-dirty}"
    return 0
  fi

  echo "v0.0.0"
}

log()  { echo "[make_dmg] $*"; }
fail() { echo "[make_dmg:ERROR] $*" >&2; exit 1; }

create_with_hdiutil() {
  log "Using hdiutil fallback (no custom Finder layout)."
  rm -rf "$STAGE_DIR" && mkdir -p "$STAGE_DIR"
  cp -R "$APP_BUNDLE" "$STAGE_DIR/"
  ln -sfn /Applications "$STAGE_DIR/Applications"
  hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$STAGE_DIR" \
    -ov -format UDZO \
    "$DMG_PATH"
}

[[ -d "$APP_BUNDLE" ]] || fail "Missing app bundle: $APP_BUNDLE. Build it first with scripts/app_build.sh."
mkdir -p "$DIST_DIR"

VERSION="$(resolve_version "${1:-}")"
DMG_NAME="$APP_NAME-${VERSION}-macOS.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
log "Resolved version: $VERSION"

[[ -f "$DMG_PATH" ]] && rm -f "$DMG_PATH"

if [[ "$PREFER_CREATE_DMG" == "1" ]] && command -v create-dmg >/dev/null 2>&1; then
  log "Using create-dmg to build $DMG_NAME"
  rm -rf "$STAGE_DIR" && mkdir -p "$STAGE_DIR"
  cp -R "$APP_BUNDLE" "$STAGE_DIR/"
  if command -v /usr/bin/python3 >/dev/null 2>&1; then
    export APP_NAME VERSION DMG_PATH STAGE_DIR CREATE_DMG_TIMEOUT_SECONDS
    if ! /usr/bin/python3 - <<PY
import os
import subprocess
import sys

cmd = [
    "create-dmg",
    "--sandbox-safe",
    "--volname",
    f"{os.environ['APP_NAME']} {os.environ['VERSION']}",
    "--window-pos",
    "200",
    "120",
    "--window-size",
    "600",
    "400",
    "--icon-size",
    "110",
    "--icon",
    f"{os.environ['APP_NAME']}.app",
    "140",
    "200",
    "--app-drop-link",
    "460",
    "200",
    os.environ["DMG_PATH"],
    os.environ["STAGE_DIR"],
]
timeout_s = int(os.environ["CREATE_DMG_TIMEOUT_SECONDS"])
try:
    subprocess.run(cmd, check=True, timeout=timeout_s)
except subprocess.TimeoutExpired:
    print(f"[make_dmg:WARN] create-dmg timed out after {timeout_s}s")
    sys.exit(124)
except subprocess.CalledProcessError as exc:
    print(f"[make_dmg:WARN] create-dmg failed with exit code {exc.returncode}")
    sys.exit(exc.returncode or 1)
PY
    then
      create_with_hdiutil
    fi
  else
    if ! create-dmg \
      --sandbox-safe \
      --volname "$APP_NAME $VERSION" \
      --window-pos 200 120 \
      --window-size 600 400 \
      --icon-size 110 \
      --icon "$APP_NAME.app" 140 200 \
      --app-drop-link 460 200 \
      "$DMG_PATH" \
      "$STAGE_DIR"; then
      create_with_hdiutil
    fi
  fi
else
  create_with_hdiutil
fi

log "DMG created: $DMG_PATH"
log "Done. To test: open \"$DMG_PATH\""
