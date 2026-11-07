#!/bin/bash
# Blackboard Sentinel - macOS Installation & Setup Script
set -e

echo "=========================================================="
echo "      Blackboard Sentinel - macOS Setup & Launcher        "
echo "=========================================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# 1. Check Python version
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is not installed or not in PATH."
    echo "Please install Python 3.10+ from https://www.python.org or via Homebrew (brew install python)."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Detected Python version: ${PY_VER}"

# 2. Virtual environment setup
VENV_DIR="${HOME}/.blackboard-sentinel/venv"
mkdir -p "${HOME}/.blackboard-sentinel"
mkdir -p "${HOME}/Library/Application Support/BlackboardSentinel"
mkdir -p "${HOME}/Library/Logs/BlackboardSentinel"

if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

echo "Installing and updating dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"

# 3. Create LaunchAgent plist for background / auto-launch at login
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_FILE="${PLIST_DIR}/com.sentinel.blackboard.plist"
mkdir -p "${PLIST_DIR}"

cat <<EOF > "${PLIST_FILE}"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sentinel.blackboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_DIR}/bin/python3</string>
        <string>${SCRIPT_DIR}/tray_app.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/BlackboardSentinel/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/BlackboardSentinel/stderr.log</string>
</dict>
</plist>
EOF

echo "Registered LaunchAgent at ${PLIST_FILE}"

# 4. Prompt to start now
read -p "Would you like to configure and start Blackboard Sentinel now? [Y/n]: " START_NOW
START_NOW=${START_NOW:-Y}

if [[ "${START_NOW}" =~ ^[Yy]$ ]]; then
    echo "Starting Blackboard Sentinel in menu bar..."
    "${VENV_DIR}/bin/python3" "${SCRIPT_DIR}/tray_app.py" &
fi

echo ""
echo "Setup complete. Blackboard Sentinel is now ready on macOS."
