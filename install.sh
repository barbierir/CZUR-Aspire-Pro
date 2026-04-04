#!/usr/bin/env bash
set -euo pipefail

APP_NAME="book-capture"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/$APP_NAME"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_NAME.desktop"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
ICON_FILE="$ICON_DIR/$APP_NAME.png"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

cp "$SCRIPT_DIR/main.py" "$INSTALL_DIR/main.py"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"

if [[ -d "$SCRIPT_DIR/assets" ]]; then
  rm -rf "$INSTALL_DIR/assets"
  cp -r "$SCRIPT_DIR/assets" "$INSTALL_DIR/assets"
fi

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi

"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/main.py" "\$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

if [[ -f "$SCRIPT_DIR/assets/icon.png" ]]; then
  cp "$SCRIPT_DIR/assets/icon.png" "$ICON_FILE"
else
  echo "Warning: assets/icon.png not found. A generic icon will be used."
fi

cp "$SCRIPT_DIR/desktop/book-capture.desktop" "$DESKTOP_FILE"
chmod 644 "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installation complete. You can launch \"Book Capture\" from the application menu."
echo "You can also run it from terminal with: $APP_NAME"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "Warning: $BIN_DIR is not currently in your PATH."
  echo "Add this line to your shell profile if needed:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi
