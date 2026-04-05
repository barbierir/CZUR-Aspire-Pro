#!/usr/bin/env bash
set -euo pipefail

APP_NAME="book-capture"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_ROOT="$ROOT_DIR/build/appimage"
APPDIR="$BUILD_ROOT/${APP_NAME}.AppDir"
DIST_DIR="$ROOT_DIR/dist"
APPIMAGE_TOOLS_DIR="$SCRIPT_DIR/tools"

REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"
MAIN_FILE="$ROOT_DIR/main.py"
ICON_FILE="$ROOT_DIR/assets/icon.png"
DESKTOP_FILE="$SCRIPT_DIR/${APP_NAME}.desktop"
APP_RUN_FILE="$SCRIPT_DIR/AppRun"

log() {
  printf '[appimage] %s\n' "$*"
}

fail() {
  printf '[appimage][error] %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

map_arch() {
  local uname_arch
  uname_arch="$(uname -m)"
  case "$uname_arch" in
    x86_64|amd64) printf 'x86_64' ;;
    aarch64|arm64) printf 'aarch64' ;;
    *) fail "Unsupported architecture: $uname_arch" ;;
  esac
}

ensure_appimagetool() {
  if command -v appimagetool >/dev/null 2>&1; then
    printf 'appimagetool'
    return
  fi

  local arch tool_url tool_path
  arch="$(map_arch)"
  tool_path="$APPIMAGE_TOOLS_DIR/appimagetool-${arch}.AppImage"

  if [[ ! -x "$tool_path" ]]; then
    mkdir -p "$APPIMAGE_TOOLS_DIR"
    tool_url="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${arch}.AppImage"
    log "Downloading appimagetool (${arch}) from ${tool_url}"

    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$tool_url" -o "$tool_path"
    elif command -v wget >/dev/null 2>&1; then
      wget -qO "$tool_path" "$tool_url"
    else
      fail "Install curl or wget to download appimagetool automatically"
    fi

    chmod +x "$tool_path"
  fi

  printf '%s' "$tool_path"
}

build_launcher() {
  local launcher="$APPDIR/usr/bin/$APP_NAME"

  cat > "$launcher" <<'LAUNCHER_EOF'
#!/usr/bin/env bash
set -euo pipefail

APPDIR="${APPDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VENV_PY="$APPDIR/usr/venv/bin/python"
APP_MAIN="$APPDIR/usr/src/main.py"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing bundled Python runtime: $VENV_PY" >&2
  exit 1
fi

if [[ ! -f "$APP_MAIN" ]]; then
  echo "Missing application entrypoint: $APP_MAIN" >&2
  exit 1
fi

PY_VER="$($VENV_PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
SITE_PKGS="$APPDIR/usr/venv/lib/python${PY_VER}/site-packages"

export PYTHONNOUSERSITE=1
if [[ -d "$SITE_PKGS/PySide6/Qt/plugins" ]]; then
  export QT_PLUGIN_PATH="$SITE_PKGS/PySide6/Qt/plugins${QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}"
fi
if [[ -d "$SITE_PKGS/PySide6/Qt/qml" ]]; then
  export QML2_IMPORT_PATH="$SITE_PKGS/PySide6/Qt/qml${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
fi
if [[ -d "$SITE_PKGS/PySide6/Qt/lib" ]]; then
  export LD_LIBRARY_PATH="$SITE_PKGS/PySide6/Qt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

exec "$VENV_PY" "$APP_MAIN" "$@"
LAUNCHER_EOF

  chmod +x "$launcher"
}

main() {
  need_cmd python3
  need_cmd rsync

  [[ -f "$MAIN_FILE" ]] || fail "File not found: $MAIN_FILE"
  [[ -f "$REQUIREMENTS_FILE" ]] || fail "File not found: $REQUIREMENTS_FILE"
  [[ -f "$DESKTOP_FILE" ]] || fail "File not found: $DESKTOP_FILE"
  [[ -f "$APP_RUN_FILE" ]] || fail "File not found: $APP_RUN_FILE"
  if [[ ! -f "$ICON_FILE" ]]; then
    log "Warning: $ICON_FILE not found, AppImage will be built without embedded icon"
  fi

  local arch output appimagetool
  arch="$(map_arch)"
  output="$DIST_DIR/${APP_NAME}-${arch}.AppImage"
  appimagetool="$(ensure_appimagetool)"

  log "Cleaning previous AppDir"
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/src" "$APPDIR/usr/share/applications"

  log "Creating virtual environment inside AppDir"
  python3 -m venv --copies "$APPDIR/usr/venv"

  log "Installing Python dependencies"
  "$APPDIR/usr/venv/bin/python" -m pip install --upgrade pip
  "$APPDIR/usr/venv/bin/python" -m pip install -r "$REQUIREMENTS_FILE"

  log "Copying application files"
  cp "$MAIN_FILE" "$APPDIR/usr/src/main.py"
  rsync -a --delete "$ROOT_DIR/assets/" "$APPDIR/usr/src/assets/"

  log "Preparing AppImage metadata files"
  cp "$APP_RUN_FILE" "$APPDIR/AppRun"
  chmod +x "$APPDIR/AppRun"

  cp "$DESKTOP_FILE" "$APPDIR/${APP_NAME}.desktop"
  cp "$DESKTOP_FILE" "$APPDIR/usr/share/applications/${APP_NAME}.desktop"
  if [[ -f "$ICON_FILE" ]]; then
    cp "$ICON_FILE" "$APPDIR/${APP_NAME}.png"
  fi

  build_launcher

  mkdir -p "$DIST_DIR"

  log "Building AppImage -> $output"
  if [[ "$appimagetool" == *.AppImage ]]; then
    ARCH="$arch" "$appimagetool" --appimage-extract-and-run "$APPDIR" "$output"
  else
    ARCH="$arch" "$appimagetool" "$APPDIR" "$output"
  fi

  log "Done. AppImage created at: $output"
}

main "$@"
