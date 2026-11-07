#!/bin/bash
# Blackboard Sentinel - macOS App & DMG Packaging Script
# Requires PyInstaller and macOS hdiutil (built-in).

set -e

echo "=========================================================="
echo "      Building Blackboard Sentinel macOS App & DMG        "
echo "=========================================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# 1. Verify build environment
if ! command -v pyinstaller &>/dev/null; then
    echo "Error: pyinstaller is not installed in the active environment."
    echo "Run: pip install pyinstaller"
    exit 1
fi

# 2. Build .app bundle via PyInstaller spec
echo "Compiling BlackboardSentinel.app bundle with PyInstaller..."
rm -rf build dist/BlackboardSentinel dist/BlackboardSentinel.app
pyinstaller --noconfirm --clean BlackboardSentinel_mac.spec

if [ ! -d "dist/BlackboardSentinel.app" ]; then
    echo "Error: dist/BlackboardSentinel.app was not created."
    exit 1
fi

echo "Successfully built dist/BlackboardSentinel.app"

# 3. Code-sign ad-hoc so macOS Gatekeeper allows running
if command -v codesign &>/dev/null; then
    echo "Ad-hoc code signing BlackboardSentinel.app..."
    codesign --force --deep --sign - "dist/BlackboardSentinel.app"
fi

# 4. Prepare staging folder for drag-and-drop DMG
DMG_STAGE="dist/dmg_staging"
DMG_OUTPUT="dist/BlackboardSentinel.dmg"

echo "Staging DMG layout..."
rm -rf "${DMG_STAGE}" "${DMG_OUTPUT}"
mkdir -p "${DMG_STAGE}"

# Copy the app bundle
cp -R "dist/BlackboardSentinel.app" "${DMG_STAGE}/"

# Create symlink to /Applications for standard drag-and-drop installer
ln -s /Applications "${DMG_STAGE}/Applications"

# 5. Build DMG using hdiutil
echo "Creating BlackboardSentinel.dmg..."
hdiutil create \
    -volname "Blackboard Sentinel" \
    -srcfolder "${DMG_STAGE}" \
    -ov \
    -format UDZO \
    "${DMG_OUTPUT}"

# Clean up staging folder
rm -rf "${DMG_STAGE}"

echo ""
echo "=========================================================="
echo "Build complete! DMG is ready at:"
echo "${SCRIPT_DIR}/${DMG_OUTPUT}"
echo "=========================================================="
