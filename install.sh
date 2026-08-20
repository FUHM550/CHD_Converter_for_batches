#!/usr/bin/env bash
# One-time installer: moves the AppImage into ~/Applications, makes it executable
# adds it to desktop's Applications menu.
# everything happens inside home folder.
# will appear in applications menu afterwards
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPIMAGE="$(find "$SCRIPT_DIR" -maxdepth 1 -iname "*.AppImage" | head -n1)"

if [ -z "$APPIMAGE" ]; then
    echo "Could not find a .AppImage file next to this script."
    echo "Put install.sh in the same folder as the downloaded .AppImage and run it again."
    read -rp "Press Enter to close..."
    exit 1
fi

APP_DIR="$HOME/Applications"
DEST="$APP_DIR/$(basename "$APPIMAGE")"

echo "Installing CHD Processing Suite to $DEST ..."
mkdir -p "$APP_DIR"
mv -f "$APPIMAGE" "$DEST"
chmod +x "$DEST"

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/chdsuite.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CHD Processing Suite
Comment=CHD/CUE/ISO batch converter and media tools
Exec=$DEST
Icon=utilities-terminal
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESKTOP_DIR/chdsuite.desktop"

echo ""
echo "Done! CHD Processing Suite is installed."
echo "  - File:  $DEST"
echo "  - It should now show up in your Applications menu as 'CHD Processing Suite'."
echo ""
read -rp "Press Enter to close this window..."
