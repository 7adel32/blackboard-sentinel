# Blackboard Sentinel

An automated course synchronizer, deadline monitor, and grade tracker for **Blackboard Learn Ultra (SaaS)** portals.

Monitors university courses in the background, automatically organizes downloaded slides/materials and assignment files into clean subject folders, and alerts you via instant messaging (Hermes Agent / Telegram / WhatsApp / CLI) when new grades, announcements, materials, or upcoming deadlines appear.

---

## Features

- **Dynamic Course Discovery**: Automatically inspects your enrolled courses directly via Blackboard's REST API and creates course folders named after each course.
- **Dual-Source Content Discovery**:
  - Traverses standard content folders, learning modules, and slide attachments.
  - Inspects assignment instructions and tests (`data-bbfile` JSON payloads) to extract homework files and project briefs that naive scrapers miss.
- **Authoritative Deadline Tracking**: Merges Blackboard calendar items with the gradebook's authoritative `grading.due` column, clamping requests to avoid API date-window drops.
- **Grade & Feedback Sentinel**: Tracks grade releases, score updates, status transitions (`NeedsGrading` → `Graded`), and instructor feedback comments.
- **Zero-Quota & Silent**: Operates purely with standard Python HTTP requests. Dispatches notifications only when updates are found; silent when nothing changes.
- **Run Anywhere**:
  - Standalone CLI execution.
  - Native Linux / WSL crontab.
  - Hermes Agent 24/7 background scheduler (`hermes cron`) with WhatsApp/Telegram push notifications.

---

## Project Structure

```text
blackboard-sentinel/
├── check_lms.py          # Main sentinel engine (syncs files, tracks deadlines & grades)
├── lms_deadlines.py      # Quick CLI helper for upcoming deadlines
├── lms_grades.py         # Quick CLI helper for recent grades & feedback
├── install.sh            # Interactive setup and Hermes installer
├── .env.example          # Environment variable template
├── requirements.txt      # Python dependencies (pure standard library)
└── skill/
    └── SKILL.md          # Hermes Agent skill definition
```

---

## Quick Start

### 1. Interactive Setup (Hermes Agent / WSL)
If you run [Hermes Agent](https://github.com/NousResearch/hermes-agent):
```bash
git clone https://github.com/<your-username>/blackboard-sentinel.git
cd blackboard-sentinel
./install.sh
```
The installer will prompt you for your student credentials and preferred storage directory, copy the files to `~/.hermes/`, and register the hourly cron job automatically.

---

### 2. Standalone Setup (Without Hermes)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/blackboard-sentinel.git
   cd blackboard-sentinel
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your login details:
   ```env
   LMS_URL="https://lms.university.edu"   # The website you enter your username and password into
   LMS_USER_ID="your_student_id"          # Your student username / ID
   LMS_PASSWORD="your_password"           # Your LMS password
   LMS_STORAGE_DIR="~/Documents/University" # Where course files should be stored
   ```

3. **Run manually:**
   ```bash
   # Check updates and sync course materials:
   python3 check_lms.py --manual

   # View upcoming deadlines:
   python3 lms_deadlines.py

   # View grades:
   python3 lms_grades.py
   ```

4. **Automate with Linux `cron`:**
   Add to `crontab -e` to run hourly:
   ```cron
   0 * * * * cd /path/to/blackboard-sentinel && /usr/bin/python3 check_lms.py >> /tmp/lms_cron.log 2>&1
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
