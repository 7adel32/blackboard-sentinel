# Blackboard Sentinel

An automated course synchronizer, deadline monitor, and grade tracker for **Blackboard Learn Ultra (SaaS)** portals.

Monitors university courses in the background, automatically organizes downloaded slides/materials and assignment files into clean subject folders, and alerts you via instant messaging (Hermes Agent / Telegram) and native Windows toast notifications when new grades, announcements, materials, or upcoming deadlines appear.

---

## Features

- **Dynamic Course Discovery**: Automatically inspects enrolled courses directly via Blackboard's REST API and creates course folders named after each course.
- **Dual-Source Content Discovery**:
  - Traverses standard content folders, learning modules, and slide attachments.
  - Inspects assignment instructions and tests (`data-bbfile` JSON payloads) to extract homework files and project briefs that naive scrapers miss.
- **Authoritative Deadline Tracking**: Merges Blackboard calendar items with the gradebook's authoritative `grading.due` column, clamping requests to avoid API date-window drops.
- **Grade & Feedback Sentinel**: Tracks grade releases, score updates, status transitions (`NeedsGrading` -> `Graded`), and instructor feedback comments.
- **Zero-Quota & Silent**: Operates purely with standard Python HTTP requests. Dispatches notifications only when updates are found; silent when nothing changes.
- **Cross-Platform**:
  - **Windows System Tray App**: Sits in notification area with dynamic state tinting, real-time animation, and quick-action menu.
  - **Windows Headless Background Task**: Runs silently via Windows Task Scheduler with zero RAM footprint when idle.
  - **Hermes Agent & Linux**: 24/7 background scheduler (`hermes cron`) inside WSL/Ubuntu with Telegram push notifications.
  - **Standalone CLI**: Runs on-demand from any terminal.

---

## Project Structure

```text
blackboard-sentinel/
├── check_lms.py          # Main sentinel engine (syncs files, tracks deadlines & grades)
├── lms_deadlines.py      # Quick CLI helper for upcoming deadlines
├── lms_grades.py         # Quick CLI helper for recent grades & feedback
├── tray_app.py           # Windows System Tray resident application
├── tray_icon.py          # State-driven tinting and animation engine
├── install.ps1           # Windows installer (Tray App or Task Scheduler)
├── uninstall.ps1         # Windows uninstaller
├── install.sh            # Linux / Hermes Agent installer
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── assets/
│   ├── icon_base.svg     # Master white base vector icon
│   ├── icon_base.png     # High-resolution (512x512) transparent base PNG
│   └── icon_base.ico     # Multi-resolution Windows icon
├── scripts/
│   └── generate_icon_png.py # Mathematical vector icon rasterizer
└── skill/
    └── SKILL.md          # Hermes Agent skill definition
```

---

## Tray Icon & Dynamic States

The Windows Tray App uses a pure white silhouette vector base (`assets/icon_base.png`) and applies real-time GPU/CPU alpha tinting:

| State | Appearance | Behavior |
| :--- | :--- | :--- |
| **synced** | Monochrome White (`#FFFFFF`) | Idle and up to date. Matches native Windows 11 system icons. |
| **working** | Animated Pulse (Sky Blue <-> White) | Actively querying Blackboard, syncing files, or checking grades. |
| **not_configured** | Warm Amber (`#F59E0B`) | Missing credentials or `.env` configuration file. |
| **error** | Crimson Red (`#EF4444`) | Connection timeout, network loss, or invalid login credentials. |
| **new_notification** | 1-Second Pulse (Emerald Gold Flash) | Plays a 1.0-second alert pulse animation and triggers native Windows Toast notifications when updates are detected. |

---

## Quick Start

### 1. Windows Installation

Run the interactive PowerShell installer or use the standalone executable:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer:
1. Installs the program into the standard Windows per-user applications folder:
   `%LOCALAPPDATA%\Programs\BlackboardSentinel\`
2. Places both `BlackboardSentinel.exe` and the dedicated `uninstall.exe` in the application folder.
3. Registers **Blackboard Sentinel** in **Windows "Installed apps" / "Add or remove programs"**.
4. Creates Start Menu and Windows Startup shortcuts.

To uninstall:
- Go to Windows **Settings -> Apps -> Installed apps -> Blackboard Sentinel -> Uninstall**, or
- Run `uninstall.exe` from the program directory or Start Menu, or
- Run `powershell -ExecutionPolicy Bypass -File .\uninstall.ps1`

---

### 2. Hermes Agent Setup (WSL / Linux)

If you run [Hermes Agent](https://github.com/NousResearch/hermes-agent):
```bash
git clone https://github.com/<your-username>/blackboard-sentinel.git
cd blackboard-sentinel
./install.sh
```
The installer prompts for credentials, installs the scripts and skill to `~/.hermes/`, and registers the hourly cron job with Telegram notifications automatically.

---

### 3. Standalone Manual CLI

1. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your login details:
   ```env
   LMS_URL="https://lms.university.edu"
   LMS_USER_ID="your_student_id"
   LMS_PASSWORD="your_password"
   LMS_STORAGE_DIR="~/Documents/University"
   ```

2. **Run on-demand:**
   ```bash
   # Check updates and sync course materials:
   python check_lms.py --manual

   # View upcoming deadlines:
   python lms_deadlines.py

   # View grades & feedback:
   python lms_grades.py
   ```

---

## Configuration Reference

| Environment Variable | Description | Default |
| :--- | :--- | :--- |
| `LMS_URL` | Base URL of your Blackboard portal (e.g. `https://lms.university.edu`) | *Required* |
| `LMS_USER_ID` | Student login username or ID number | *Required* |
| `LMS_PASSWORD` | Student login password | *Required* |
| `LMS_STORAGE_DIR` | Local root directory for downloaded course materials | `~/Documents/University` |
| `LMS_STUDENT_ID` | Internal Blackboard user ID (auto-detected if omitted) | Auto-detected |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
