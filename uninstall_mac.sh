#!/bin/bash
# Blackboard Sentinel - macOS Uninstaller Script

echo "=========================================================="
echo "      Blackboard Sentinel - macOS Uninstaller             "
echo "=========================================================="
echo ""

# 1. Terminate running process
echo "Stopping any running instances..."
pkill -f "tray_app.py" 2>/dev/null || true
pkill -f "BlackboardSentinel" 2>/dev/null || true

# 2. Unload and remove LaunchAgent
PLIST_FILE="${HOME}/Library/LaunchAgents/com.sentinel.blackboard.plist"
if [ -f "${PLIST_FILE}" ]; then
    echo "Unloading LaunchAgent..."
    launchctl unload "${PLIST_FILE}" 2>/dev/null || true
    rm -f "${PLIST_FILE}"
fi

# 3. Clean up virtualenv and application support
echo "Cleaning up files..."
rm -rf "${HOME}/.blackboard-sentinel"
rm -rf "${HOME}/Library/Application Support/BlackboardSentinel"
rm -rf "${HOME}/Library/Logs/BlackboardSentinel"

# 4. Remove credentials from macOS Keychain if available
python3 -c '
try:
    import keyring
    keyring.delete_password("BlackboardSentinel", "")
except Exception:
    pass
' 2>/dev/null || true

echo "Uninstallation complete. Blackboard Sentinel has been removed."
