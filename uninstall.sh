#!/usr/bin/env bash
set -euo pipefail

APP_NAME="book-capture"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
LAUNCHER="$HOME/.local/bin/$APP_NAME"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_NAME.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/256x256/apps/$APP_NAME.png"

rm -rf "$INSTALL_DIR"
rm -f "$LAUNCHER"
rm -f "$DESKTOP_FILE"
rm -f "$ICON_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Book Capture was removed from your user profile."
