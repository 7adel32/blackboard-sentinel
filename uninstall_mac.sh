#!/bin/bash
# Blackboard Sentinel - macOS Uninstaller Script

echo "=========================================================="
echo "      Blackboard Sentinel - macOS Uninstaller             "
echo "=========================================================="
echo ""

# 1. Terminate running process
echo "Stopping any running instances..."
PID_FILE="${HOME}/Library/Application Support/BlackboardSentinel/tray_app.pid"
if [ -f "${PID_FILE}" ]; then
    PID=$(cat "${PID_FILE}" 2>/dev/null || true)
    if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
        kill "${PID}" 2>/dev/null || true
    fi
fi
pkill -f "tray_app.py" 2>/dev/null || true
pkill -f "BlackboardSentinel.app/Contents/MacOS/BlackboardSentinel" 2>/dev/null || true

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
if command -v security &>/dev/null; then
    while security delete-generic-password -s "BlackboardSentinel" >/dev/null 2>&1; do
        :
    done
fi

echo "Uninstallation complete. Blackboard Sentinel has been removed."
