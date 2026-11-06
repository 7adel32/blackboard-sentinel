---
name: university-portal
description: "University LMS deadlines, assignments, submissions, grades, and Blackboard tracking. Trigger whenever the user asks about deadlines, Deadlines, assignments, due dates, calendar, grades, or LMS."
version: 1.1.0
tags: [LMS, University, Grades, Deadlines, Academic, Blackboard]
---

# University Portal Skill

Whenever the user asks about university deadlines or grades (including single-word messages like "Deadlines", "deadlines", "grades", "Grades", "/deadlines", "/grades"):
**DO NOT search local files, do not use search_files or explore directories.**
Execute the dedicated Python script immediately via the terminal tool and reply with its output.

## Triggers & Actions

1. **Deadlines / Due Dates / Assignments / Calendar**:
   - Matches: `"Deadlines"`, `"deadlines"`, `"what are my deadlines"`, `"/deadlines"`, `"due dates"`, `"assignments"`
   - Command:
     ```bash
     python3 ~/.hermes/scripts/lms_deadlines.py
     ```
   - Reply directly with the script output.

2. **Grades / Marks / Feedback / Score**:
   - Matches: `"Grades"`, `"grades"`, `"what are my grades"`, `"/grades"`, `"marks"`, `"results"`
   - Command:
     ```bash
     python3 ~/.hermes/scripts/lms_grades.py
     ```
   - Reply directly with the script output.

## Reply Notes

- Each deadline entry includes a Status: line: SUBMITTED, NOT SUBMITTED, or UNVERIFIED (no gradebook record). Graded items are omitted. Mention clearly when an upcoming item is NOT SUBMITTED.
- The sentinel cron job (`check_lms.py`) also writes a local deadline cache that offline reminder checks can read without calling the portal.

## Optional Environment Settings (`~/.hermes/.env`)

- `LMS_MAX_WORKERS`: parallel course checking threads. `0` (default) = unlimited (capped at 16 internally), `1` = sequential for very old single-core machines.
- `LMS_MAX_FILE_SIZE_MB`: skip downloading files larger than this size. `0` (default) = disabled.
- `LMS_EXPAND_ZIPS`: automatically decompress imported `.zip` files into `<name>_zip` in the same folder (`false` by default; compute intensive and not suitable for low-power machines).
- `LMS_DELETE_ORIGINAL_ZIP`: delete the original `.zip` file after decompression (`false` by default).
