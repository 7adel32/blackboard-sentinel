#!/usr/bin/env python3
"""
Blackboard Sentinel command-line runner.

A console executable with simple, predictable subcommands and plain-text or JSON output,
so scripts and automated agents never need to drive the tray app or its windows.

Usage:
    BlackboardSentinelCLI <command> [options]

Commands:
    status      Show configuration state and cached deadline summary (no network)
    check       Run a full sync now (files, announcements, grades, deadlines)
    deadlines   List upcoming deadlines with submission status   [--json] [--notify]
    grades      List current grades and feedback                 [--json] [--notify]
    courses     List monitored courses                           [--json]
    help        Show this message

Exit code: 0 on success, 1 on error (a line starting with "ERROR:" is printed to stderr).
"""

import os
import sys
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

HELP = __doc__.strip()


def _fail(msg):
    sys.stderr.write(f"ERROR: {msg}\n")
    return 1


def _require_config(check_lms):
    check_lms.init_config()
    if not check_lms.is_configured():
        raise RuntimeError(
            "LMS credentials are not configured. Run BlackboardSentinel.exe --setup once, "
            "or set LMS_URL, LMS_USER_ID and LMS_PASSWORD in the environment or .env."
        )


def cmd_status(args):
    import check_lms
    check_lms.init_config()
    configured = check_lms.is_configured()
    state = check_lms.load_state() if configured else {}
    cache = (state.get("deadline_cache") or {}).get("items", [])
    info = {
        "configured": configured,
        "lms_url": check_lms.LMS_URL,
        "storage_dir": check_lms.LMS_STORAGE_DIR,
        "state_file": check_lms.STATE_FILE,
        "max_workers": check_lms.MAX_WORKERS,
        "max_file_size_mb": round(check_lms.MAX_FILE_BYTES / 1048576, 2),
        "cached_deadlines": len(cache),
        "tracked_files": len(state.get("seen_files", [])),
        "tracked_grades": len(state.get("seen_grades", {})),
    }
    if "--json" in args:
        print(json.dumps(info, indent=2))
    else:
        for k, v in info.items():
            print(f"{k}: {v}")
    return 0 if configured else 1


def cmd_check(args):
    import check_lms
    _require_config(check_lms)
    sys.argv = ["check_lms.py", "--manual"]
    check_lms.main()
    return 0


def cmd_deadlines(args):
    import lms_deadlines
    if "--json" not in args:
        sys.argv = ["lms_deadlines.py"] + [a for a in args]
        lms_deadlines.main()
        return 0
    items = lms_deadlines.get_deadlines()
    out = []
    for it in items:
        row = dict(it)
        row["due_utc"] = row.pop("due_dt").isoformat()
        out.append(row)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_grades(args):
    import lms_grades
    if "--json" not in args:
        sys.argv = ["lms_grades.py"] + [a for a in args]
        lms_grades.main()
        return 0
    print(json.dumps(lms_grades.get_all_grades(), indent=2, ensure_ascii=False))
    return 0


def cmd_courses(args):
    import check_lms
    _require_config(check_lms)
    client = check_lms.LMSClient(check_lms.USER_ID, check_lms.PASSWORD)
    client.login()
    courses = check_lms.get_courses_map(client)
    rows = [
        {"id": cid, "name": c.get("name", ""), "code": c.get("code", ""), "doctor": c.get("doctor", "")}
        for cid, c in courses.items()
    ]
    if "--json" in args:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{r['id']}: {r['name']} ({r['code']}) - {r['doctor']}")
    return 0


COMMANDS = {
    "status": cmd_status,
    "check": cmd_check,
    "deadlines": cmd_deadlines,
    "grades": cmd_grades,
    "courses": cmd_courses,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(HELP)
        return 0
    cmd, rest = argv[0].lower(), argv[1:]
    handler = COMMANDS.get(cmd)
    if handler is None:
        sys.stderr.write(f"ERROR: unknown command '{cmd}'\n")
        print(HELP)
        return 1
    try:
        return handler(rest)
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:
        return _fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
