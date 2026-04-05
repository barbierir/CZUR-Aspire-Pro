#!/usr/bin/env bash
set -euo pipefail

APP_NAME="book-capture"
APP_VERSION="0.1.0"
APP_ARCH="amd64"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/deb/$APP_NAME"
DIST_DIR="$ROOT_DIR/dist"
OUTPUT_DEB="$DIST_DIR/${APP_NAME}_${APP_VERSION}_${APP_ARCH}.deb"

CONTROL_FILE="$SCRIPT_DIR/control"
POSTINST_FILE="$SCRIPT_DIR/postinst"
MAIN_FILE="$ROOT_DIR/main.py"
REQ_FILE="$ROOT_DIR/requirements.txt"
ASSETS_DIR="$ROOT_DIR/assets"
DESKTOP_FILE="$ROOT_DIR/desktop/${APP_NAME}.desktop"
ICON_FILE="$ROOT_DIR/assets/icon.png"

log() {
  printf '[deb] %s\n' "$*"
}

fail() {
  printf '[deb][error] %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Comando richiesto non trovato: $1"
}

need_file() {
  [[ -e "$1" ]] || fail "File o cartella mancante: $1"
}

main() {
  need_cmd python3
  need_cmd dpkg-deb

  if ! python3 -m venv --help >/dev/null 2>&1; then
    fail "Modulo venv non disponibile. Installa il pacchetto python3-venv."
  fi

  need_file "$CONTROL_FILE"
  need_file "$POSTINST_FILE"
  need_file "$MAIN_FILE"
  need_file "$REQ_FILE"
  need_file "$ASSETS_DIR"
  need_file "$DESKTOP_FILE"
  need_file "$ICON_FILE"

  log "Pulizia cartella build precedente"
  rm -rf "$BUILD_DIR"

  log "Creazione struttura filesystem Debian"
  mkdir -p \
    "$BUILD_DIR/DEBIAN" \
    "$BUILD_DIR/opt/$APP_NAME" \
    "$BUILD_DIR/usr/bin" \
    "$BUILD_DIR/usr/share/applications" \
    "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"

  log "Copia metadati pacchetto"
  cp "$CONTROL_FILE" "$BUILD_DIR/DEBIAN/control"
  cp "$POSTINST_FILE" "$BUILD_DIR/DEBIAN/postinst"
  chmod 0755 "$BUILD_DIR/DEBIAN/postinst"

  log "Copia file applicazione"
  cp "$MAIN_FILE" "$BUILD_DIR/opt/$APP_NAME/main.py"
  cp "$REQ_FILE" "$BUILD_DIR/opt/$APP_NAME/requirements.txt"
  cp -a "$ASSETS_DIR" "$BUILD_DIR/opt/$APP_NAME/assets"

  log "Creazione virtualenv isolato"
  python3 -m venv --copies "$BUILD_DIR/opt/$APP_NAME/venv"

  log "Installazione dipendenze Python nel virtualenv"
  "$BUILD_DIR/opt/$APP_NAME/venv/bin/python" -m pip install --upgrade pip
  "$BUILD_DIR/opt/$APP_NAME/venv/bin/python" -m pip install -r "$BUILD_DIR/opt/$APP_NAME/requirements.txt"

  log "Creazione launcher CLI /usr/bin/$APP_NAME"
  cat > "$BUILD_DIR/usr/bin/$APP_NAME" <<'LAUNCHER_EOF'
#!/usr/bin/env bash
exec /opt/book-capture/venv/bin/python /opt/book-capture/main.py "$@"
LAUNCHER_EOF
  chmod 0755 "$BUILD_DIR/usr/bin/$APP_NAME"

  log "Installazione desktop entry e icona"
  cp "$DESKTOP_FILE" "$BUILD_DIR/usr/share/applications/$APP_NAME.desktop"
  cp "$ICON_FILE" "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"

  mkdir -p "$DIST_DIR"

  log "Build pacchetto Debian"
  dpkg-deb --build "$BUILD_DIR" "$OUTPUT_DEB"

  log "Pacchetto creato: $OUTPUT_DEB"
}

main "$@"
