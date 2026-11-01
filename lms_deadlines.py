#!/usr/bin/env python3
"""
Manual On-Demand LMS Deadlines Viewer
University Academic LMS Portal
"""

import sys
import os
import argparse
import subprocess
import json
from datetime import datetime, timezone, timedelta

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
hermes_scripts = os.path.expanduser("~/.hermes/scripts")
if os.path.exists(hermes_scripts) and hermes_scripts not in sys.path:
    sys.path.append(hermes_scripts)

from check_lms import LMSClient, get_courses_map, AST_TZ, init_config, is_configured
import check_lms


def get_deadlines():
    init_config()
    if not is_configured():
        raise RuntimeError("LMS credentials not configured in .env or environment.")
    client = LMSClient(check_lms.USER_ID, check_lms.PASSWORD)
    client.login()
    now = datetime.now(timezone.utc)

    since_str = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    until_str = (now + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    candidates = {}

    # 1. Blackboard Calendar
    cal = client.get_json(f"/learn/api/public/v1/calendars/items?since={since_str}&until={until_str}")
    if cal and "results" in cal:
        for it in cal["results"]:
            due_str = it.get("end") or it.get("start")
            if due_str:
                item_id = it.get("id") or f"{it.get('calendarId')}_{it.get('title')}"
                candidates[item_id] = {
                    "cid": it.get("calendarId"),
                    "title": it.get("title"),
                    "due_str": due_str
                }

    # 2. Gradebook Columns
    courses_map = get_courses_map(client)
    for cid in courses_map.keys():
        cols = client.get_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns")
        if cols and "results" in cols:
            for c in cols["results"]:
                due_str = c.get("grading", {}).get("due")
                col_id = c.get("id")
                if due_str and col_id not in candidates:
                    candidates[col_id] = {
                        "cid": cid,
                        "title": c.get("name"),
                        "due_str": due_str
                    }

    # Load state to filter out already graded / submitted items
    state_file = os.path.expanduser("~/.hermes/state/lms_tracker_state.json")
    seen_grades = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f_st:
                seen_grades = json.load(f_st).get("seen_grades", {})
        except Exception:
            pass

    upcoming = []
    for item_id, it in candidates.items():
        cid = it["cid"]
        col_id = item_id

        # Skip if student has already completed or received a grade for this item
        grade_entry = seen_grades.get(f"{cid}_{col_id}")
        if not grade_entry:
            for k, v in seen_grades.items():
                if k.startswith(f"{cid}_") and v.get("name", "").strip().lower() == it["title"].strip().lower():
                    grade_entry = v
                    break

        if grade_entry:
            g_status = grade_entry.get("status")
            g_score = grade_entry.get("score")
            if g_status in ("Graded", "NeedsGrading") or g_score is not None:
                continue

        try:
            due_dt = datetime.fromisoformat(it["due_str"].replace("Z", "+00:00"))
        except Exception:
            continue

        hours_left = (due_dt - now).total_seconds() / 3600.0
        if hours_left < 0:
            continue

        course_info = courses_map.get(it["cid"], {"name": "Course", "code": "", "doctor": ""})
        due_ast = due_dt.astimezone(AST_TZ)

        days_val = hours_left / 24.0
        if hours_left < 24:
            countdown = f"{int(hours_left)} hours left"
        else:
            countdown = f"{days_val:.1f} days left"

        upcoming.append({
            "course": f"{course_info['name']} ({course_info['code']})",
            "doctor": course_info["doctor"],
            "title": it["title"],
            "due_dt": due_dt,
            "due_str": due_ast.strftime("%A, %b %d, %Y at %I:%M %p AST"),
            "countdown": countdown
        })

    upcoming.sort(key=lambda x: x["due_dt"])
    return upcoming


def main():
    parser = argparse.ArgumentParser(description="View upcoming LMS deadlines on-demand.")
    parser.add_argument("--telegram", "-t", action="store_true", help="Also send output to Telegram.")
    args = parser.parse_args()

    items = get_deadlines()

    if not items:
        out = "[Deadlines] LMS Upcoming Deadlines\n\nNo upcoming active deadlines found on Blackboard."
    else:
        lines = ["[Deadlines] Upcoming LMS Deadlines\n"]
        for i, it in enumerate(items, 1):
            lines.append(
                f"{i}. [Task] **{it['title']}**\n"
                f"   *Course*: {it['course']}\n"
                f"   *Instructor*: {it['doctor']}\n"
                f"   *Due*: {it['due_str']} ({it['countdown']})\n"
            )
        out = "\n".join(lines).strip()

    print(out)

    if args.telegram:
        subprocess.run(["hermes", "send", "--to", "telegram", out], check=False)


if __name__ == "__main__":
    main()
