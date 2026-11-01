#!/usr/bin/env python3
"""
Manual On-Demand LMS Grades & Feedback Viewer
University Academic LMS Portal
"""

import sys
import os
import argparse
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
hermes_scripts = os.path.expanduser("~/.hermes/scripts")
if os.path.exists(hermes_scripts) and hermes_scripts not in sys.path:
    sys.path.append(hermes_scripts)

from check_lms import LMSClient, get_courses_map, clean_html, init_config, is_configured
import check_lms


def get_all_grades():
    init_config()
    if not is_configured():
        raise RuntimeError("LMS credentials not configured in .env or environment.")
    client = LMSClient(check_lms.USER_ID, check_lms.PASSWORD)
    client.login()

    courses_data = []

    courses_map = get_courses_map(client)
    for cid, info in courses_map.items():
        cols = client.get_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns")
        if not cols or "results" not in cols:
            continue

        c_grades = []
        for col in cols["results"]:
            col_id = col.get("id")
            col_name = col.get("name") or "Item"

            grade_data = client.get_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns/{col_id}/users/{getattr(client, "student_user_id", "")}")
            if not grade_data:
                continue

            status = grade_data.get("status")
            dg = grade_data.get("displayGrade", {})
            score = dg.get("score")
            possible = dg.get("possible")
            feedback = clean_html(grade_data.get("feedback", ""))

            # Inspect underlying student attempt to distinguish InProgress (draft/opened) from submitted
            attempt_status = None
            if status == "NeedsGrading" or score is None:
                att_data = client.get_json(f"/learn/api/public/v1/courses/{cid}/gradebook/columns/{col_id}/attempts")
                if att_data and "results" in att_data and att_data["results"]:
                    attempt_status = att_data["results"][-1].get("status")

            # Ignore items that have no grade and no completed submission (e.g. untouched or just opened/in-progress)
            if score is None and attempt_status in ("InProgress", None):
                continue

            c_grades.append({
                "name": col_name,
                "score": score,
                "possible": possible,
                "status": status,
                "attempt_status": attempt_status,
                "feedback": feedback
            })

        courses_data.append({
            "course": f"{info['name']} ({info['code']})",
            "doctor": info["doctor"],
            "grades": c_grades
        })

    return courses_data


def send_to_chat(text, platform=None):
    if not text:
        return
    target_platform = platform or os.getenv("HERMES_CHAT_PLATFORM", "whatsapp").strip().lower()
    try:
        cmd = ["hermes", "send", "--to", target_platform, text]
        res = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            return
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            cmd = ["wsl.exe", "-e", "hermes", "send", "--to", target_platform, text]
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="View all current LMS grades on-demand.")
    parser.add_argument("--notify", "-n", "-t", "--telegram", "--chat", action="store_true", help="Push notification to messaging chat (default: whatsapp).")
    parser.add_argument("--to", default=os.getenv("HERMES_CHAT_PLATFORM", "whatsapp"), help="Target messaging platform (default: whatsapp).")
    args = parser.parse_args()

    data = get_all_grades()

    lines = ["[Grades] University Academic Grades & Evaluation\n"]

    for c in data:
        lines.append(f"**{c['course']}** *({c['doctor']})*")
        if not c["grades"]:
            lines.append("   *No posted grades yet.*\n")
            continue

        for g in c["grades"]:
            # Format score
            score = g["score"]
            pos = g["possible"]
            status = g["status"]

            if score is not None and pos:
                pct = (score / pos) * 100.0
                grade_str = f"**{score} / {pos}** ({pct:.1f}%)"
            elif score is not None:
                grade_str = f"**{score}**"
            elif status == "NeedsGrading":
                grade_str = "*Submitted (Under Review)*"
            elif status:
                grade_str = f"*{status}*"
            else:
                grade_str = "—"

            lines.append(f"   • {g['name']}: {grade_str}")
            if g["feedback"]:
                lines.append(f"     *Feedback*: {g['feedback']}")
        lines.append("")

    out = "\n".join(lines).strip()
    print(out)

    if args.notify:
        send_to_chat(out, platform=args.to)


if __name__ == "__main__":
    main()
