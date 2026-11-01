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
- **Minimal Resource Footprint**:
  - **Windows Tray App**: Sits idle in the notification area at only ~25–35 MB RAM.
  - **Hermes Agent & Linux**: **0 MB** idle RAM (runs on-demand via `hermes cron`, taking ~18 MB for 3–5 seconds during checks and terminating immediately).
- **Zero-Quota & Silent**: Operates purely with standard Python HTTP requests. Dispatches notifications only when updates are found; silent when nothing changes.
- **Cross-Platform**:
  - **Windows System Tray App**: Sits in notification area as a real-time status indicator with dynamic state tinting, waiting animation, and quick-action menu.
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

### 1. Windows Installation (Recommended)

1. **Download the Setup Executable**:
   Download **`BlackboardSentinelSetup.exe`** from the [Latest Release](https://github.com/7adel32/blackboard-sentinel/releases/latest).

2. **Run the Installer**:
   Double-click `BlackboardSentinelSetup.exe` and click **Install / Update**.

*(Alternative: install from source via PowerShell)*:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

To uninstall:
- Go to Windows **Settings -> Apps -> Installed apps -> Blackboard Sentinel -> Uninstall**, or
- Run **Uninstall Blackboard Sentinel** from your Start Menu, or
- Run `uninstall.exe` directly from `%LOCALAPPDATA%\Programs\BlackboardSentinel\`

---

### 2. Standalone Manual CLI (Cross-Platform)

For headless servers, Linux, or command-line usage without the desktop tray:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/7adel32/blackboard-sentinel.git
   cd blackboard-sentinel
   pip install -r requirements.txt
   ```

2. **Configure credentials:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your portal details:
   ```env
   LMS_URL="https://lms.university.edu"
   LMS_USER_ID="your_student_id"
   LMS_PASSWORD="your_password"
   LMS_STORAGE_DIR="~/Documents/University"
   ```

3. **Run on-demand:**
   ```bash
   # Check updates and sync course materials:
   python check_lms.py --manual

   # View upcoming deadlines:
   python lms_deadlines.py

   # View grades and feedback:
   python lms_grades.py
   ```

---

## 24/7 Telegram Notifications via Hermes Agent (Optional)

If you run [Hermes Agent](https://github.com/NousResearch/hermes-agent) on Linux or WSL with Telegram configured, you can run Sentinel as an automated 24/7 background watchdog:

```bash
chmod +x install.sh && ./install.sh
```

The installer:
1. Prompts for credentials (or reads existing `.env` from `~/.hermes/.env`).
2. Copies sentinel scripts to `~/.hermes/scripts/`.
3. Installs the `university-portal` skill to `~/.hermes/skills/`.
4. Automatically registers an hourly cron job (`lms-sentinel`) with origin Telegram delivery.

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
