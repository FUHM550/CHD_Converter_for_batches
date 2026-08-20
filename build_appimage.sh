#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Uses project-local venv (has appimage-builder) and .tools (has appimagetool)
if [ -f "$ROOT/.build_venv/bin/activate" ]; then
    source "$ROOT/.build_venv/bin/activate"
fi
export PATH="$ROOT/.tools:$PATH"

BUILD_ROOT="/tmp/chd-appimage-build"

echo "==> Cleaning previous build dir ($BUILD_ROOT)"
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT/AppDir/usr/src"

echo "==> Staging application source"
cp "$ROOT/AppImageBuilder.yml" "$BUILD_ROOT/"
cp "$ROOT/main_launcher.py" "$ROOT/chd_gui_advanced.py" "$ROOT/chd_gui.py" \
   "$ROOT/ape_to_flac_preprocessor.py" "$ROOT/chd_extractor_core.py" \
   "$BUILD_ROOT/AppDir/usr/src/"

echo "==> Running appimage-builder in $BUILD_ROOT"
cd "$BUILD_ROOT"
appimage-builder --recipe AppImageBuilder.yml

echo "==> Copying built AppImage back to project"
mv -v ./*.AppImage "$ROOT/"

echo "==> Done: $(ls "$ROOT"/*.AppImage)"
