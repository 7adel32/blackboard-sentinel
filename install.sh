#!/bin/bash
set -e

echo "=========================================================="
echo "      University LMS Portal Skill & Sentinel Installer    "
echo "=========================================================="
echo ""

HERMES_DIR="${HOME}/.hermes"
ENV_FILE="${HERMES_DIR}/.env"

mkdir -p "${HERMES_DIR}/scripts"
mkdir -p "${HERMES_DIR}/skills/university-portal"
mkdir -p "${HERMES_DIR}/state"
mkdir -p "${HERMES_DIR}/logs"
touch "${ENV_FILE}"

# 1. Prompt for university portal URL and credentials
CURRENT_USER=$(grep -E "^LMS_USER_ID=" "${ENV_FILE}" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)

if [ -z "${CURRENT_USER}" ]; then
    echo "Please configure your University Blackboard Portal:"
    echo "Enter your university's LMS Base URL (the website where you enter your username and password):"
    read -p "LMS Base URL (e.g. https://lms.university.edu): " INPUT_URL
    while [ -z "${INPUT_URL}" ]; do
        echo "LMS URL cannot be empty."
        read -p "LMS Base URL (e.g. https://lms.university.edu): " INPUT_URL
    done
    # Strip trailing slash if present
    INPUT_URL="${INPUT_URL%/}"

    echo ""
    echo "Enter your login credentials:"
    read -p "Username / Student ID: " INPUT_USER
    read -s -p "Password: " INPUT_PASS
    echo ""

    echo "" >> "${ENV_FILE}"
    echo "# University LMS Credentials" >> "${ENV_FILE}"
    echo "LMS_URL=\"${INPUT_URL}\"" >> "${ENV_FILE}"
    echo "LMS_USER_ID=\"${INPUT_USER}\"" >> "${ENV_FILE}"
    echo "LMS_PASSWORD=\"${INPUT_PASS}\"" >> "${ENV_FILE}"
    echo "-> Saved credentials securely to ~/.hermes/.env"
else
    echo "-> Found existing LMS credentials for ${CURRENT_USER} in ~/.hermes/.env"
fi

# 2. Prompt for download storage folder
CURRENT_DIR=$(grep -E "^LMS_STORAGE_DIR=" "${ENV_FILE}" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)

if [ -z "${CURRENT_DIR}" ]; then
    DEFAULT_STORAGE="${HOME}/Documents/University"
    echo ""
    echo "Where would you like course files, assignments, and slides stored?"
    read -p "Storage directory [default: ${DEFAULT_STORAGE}]: " INPUT_DIR
    INPUT_DIR=${INPUT_DIR:-${DEFAULT_STORAGE}}

    # Expand tilde if provided
    INPUT_DIR="${INPUT_DIR/#\~/$HOME}"
    mkdir -p "${INPUT_DIR}"

    echo "LMS_STORAGE_DIR=\"${INPUT_DIR}\"" >> "${ENV_FILE}"
    echo "-> Storage directory configured: ${INPUT_DIR}"
    echo "-> Subfolders will be created automatically using your course names from Blackboard."
else
    echo "-> Found existing storage directory: ${CURRENT_DIR}"
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 3. Copy scripts & skill
cp "${DIR}/check_lms.py" "${HERMES_DIR}/scripts/"
cp "${DIR}/lms_deadlines.py" "${HERMES_DIR}/scripts/"
cp "${DIR}/lms_grades.py" "${HERMES_DIR}/scripts/"
chmod +x "${HERMES_DIR}/scripts/"*.py
cp "${DIR}/skill/SKILL.md" "${HERMES_DIR}/skills/university-portal/"

echo "-> Installed scripts and university-portal skill."

# 4. Schedule cron job
if command -v hermes &> /dev/null; then
    echo "-> Registering lms-sentinel watchdog in Hermes cron..."
    hermes cron create "60m" --name "lms-sentinel" --script "check_lms.py" --no-agent --deliver origin || true
fi

echo ""
echo "Installation complete! Everything is configured."
