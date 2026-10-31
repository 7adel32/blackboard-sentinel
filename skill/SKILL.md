---
name: university-portal
description: "University LMS deadlines, assignments, submissions, grades, and Blackboard tracking for University of Tabuk. Trigger whenever the user asks about deadlines, Deadlines, assignments, due dates, calendar, grades, or LMS."
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
