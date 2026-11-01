"""
Blackboard Sentinel - Windows System Tray Resident Application
Supports state-driven tinting, real-time animation, scheduled background checks,
and native Windows toast notifications.
"""

import os
import sys
import time
import math
import threading
import subprocess
import webbrowser
from datetime import datetime

import pystray
from PIL import Image

import check_lms
from tray_icon import TrayIconTheme


class SentinelTrayApp:
    def __init__(self, check_interval_minutes=60):
        self.check_interval_seconds = check_interval_minutes * 60
        self.theme = TrayIconTheme(target_size=64)
        
        check_lms.init_config()
        if not check_lms.is_configured():
            self.current_state = TrayIconTheme.STATE_NOT_CONFIGURED
            self.last_status_message = "Credentials missing in .env"
        else:
            self.current_state = TrayIconTheme.STATE_SYNCED
            self.last_status_message = "Ready"
        
        self.is_running = True
        self.is_checking = False
        self.last_check_time = None
        self.state_start_time = time.time()
        self._anim_thread = None
        self._check_thread = None
        self.icon = None

    def get_tooltip(self):
        if self.current_state == TrayIconTheme.STATE_WORKING:
            msg = self.last_status_message or "Checking LMS..."
            return f"Blackboard Sentinel: {msg}"
        elif self.current_state == TrayIconTheme.STATE_NOT_CONFIGURED:
            return "Blackboard Sentinel: Not Configured (Missing .env)"
        elif self.current_state == TrayIconTheme.STATE_ERROR:
            return f"Blackboard Sentinel: Error ({self.last_status_message})"
        
        if self.last_check_time:
            time_str = self.last_check_time.strftime("%I:%M %p")
            return f"Blackboard Sentinel: Up to date (Last check: {time_str})"
        return "Blackboard Sentinel: Idle"

    def set_state(self, state, message=""):
        self.current_state = state
        self.state_start_time = time.time()
        if message:
            self.last_status_message = message
        if self.icon:
            self.icon.title = self.get_tooltip()
            # Immediately update image for non-animated or starting state
            self.icon.icon = self.theme.get_image(self.current_state, 0.0)

    def animation_loop(self):
        """Dedicated loop updating tray icon during dynamic animated states."""
        while self.is_running:
            if not self.icon:
                time.sleep(0.1)
                continue

            elapsed = time.time() - self.state_start_time

            if self.current_state == TrayIconTheme.STATE_WORKING:
                # Continuous pulsing while actively checking
                self.icon.icon = self.theme.get_image(self.current_state, elapsed)
                time.sleep(0.06)

            elif self.current_state == TrayIconTheme.STATE_ERROR:
                # Continuous pulsing breathing animation in error state
                self.icon.icon = self.theme.get_image(self.current_state, elapsed)
                time.sleep(0.06)

            elif self.current_state == TrayIconTheme.STATE_NEW_NOTIFICATION:
                if elapsed <= 1.0:
                    # 1-second pulse animation
                    self.icon.icon = self.theme.get_image(self.current_state, elapsed)
                    time.sleep(0.05)
                else:
                    # Animation finished: return to synced state
                    self.set_state(TrayIconTheme.STATE_SYNCED)
                    time.sleep(0.1)

            else:
                # Static states (synced, error, not_configured) sleep gently
                time.sleep(0.3)

    def trigger_check_async(self):
        if self.is_checking:
            return
        threading.Thread(target=self._run_check_worker, daemon=True).start()

    def _run_check_worker(self):
        self.is_checking = True
        self.set_state(TrayIconTheme.STATE_WORKING, "Syncing courses and grades...")

        check_lms.init_config()
        if not check_lms.is_configured():
            self.set_state(TrayIconTheme.STATE_NOT_CONFIGURED, "Credentials missing in .env")
            self.is_checking = False
            return

        try:
            state = check_lms.load_state()
            client = check_lms.LMSClient(check_lms.USER_ID, check_lms.PASSWORD)
            client.login()

            all_downloads = []
            all_new_requests = []
            all_announcements = []
            all_external_links = []

            courses_dict = check_lms.get_courses_map(client)
            for cid, info in courses_dict.items():
                dl, new_reqs, ext_links = check_lms.check_and_download_course_files(client, cid, info, state)
                all_downloads.extend(dl)
                all_new_requests.extend(new_reqs)
                all_external_links.extend(ext_links)
                ann = check_lms.check_announcements(client, cid, info, state)
                all_announcements.extend(ann)

            all_grades = check_lms.check_grades(client, state, courses_map=courses_dict)
            all_deadlines = check_deadlines_list = check_lms.check_deadlines(client, state, courses_map=courses_dict)
            check_lms.save_state(state)

            has_updates = bool(all_downloads or all_new_requests or all_announcements or all_grades or all_deadlines)
            self.last_check_time = datetime.now()

            if has_updates:
                # Trigger 1-second notification animation
                self.set_state(TrayIconTheme.STATE_NEW_NOTIFICATION, "New updates detected")

                messages = check_lms.format_update_messages(
                    all_downloads=all_downloads,
                    all_new_requests=all_new_requests,
                    all_announcements=all_announcements,
                    all_grades=all_grades,
                    all_deadlines=all_deadlines,
                    all_external_links=all_external_links
                )
                if messages:
                    combined_text = "\n\n---\n\n".join(messages).strip()
                    check_lms.send_notification(combined_text, "Blackboard Sentinel")

                # Compose concise toast summary
                summary_parts = []
                if all_grades:
                    summary_parts.append(f"{len(all_grades)} new grade(s)")
                if all_downloads:
                    summary_parts.append(f"{len(all_downloads)} new file(s)")
                if all_new_requests:
                    summary_parts.append(f"{len(all_new_requests)} new assignment(s)")
                if all_deadlines:
                    summary_parts.append(f"{len(all_deadlines)} upcoming deadline(s)")
                if all_announcements:
                    summary_parts.append(f"{len(all_announcements)} announcement(s)")

                summary_text = ", ".join(summary_parts) if summary_parts else "Updates found"
                if self.icon:
                    try:
                        self.icon.notify(summary_text, "Blackboard Sentinel")
                    except Exception:
                        check_lms.send_windows_toast("Blackboard Sentinel", summary_text)
            else:
                self.set_state(TrayIconTheme.STATE_SYNCED, "All courses up to date")

        except Exception as e:
            self.set_state(TrayIconTheme.STATE_ERROR, str(e))
        finally:
            self.is_checking = False

    def scheduler_loop(self):
        """Background thread executing periodic checks."""
        # Initial check after 5 seconds of launch
        time.sleep(5)
        while self.is_running:
            self.trigger_check_async()
            # Wait for next interval in small slices to respond quickly to shutdown
            for _ in range(int(self.check_interval_seconds / 2)):
                if not self.is_running:
                    return
                time.sleep(2)

    # Context Menu Actions
    def on_check_now(self, icon, item):
        self.trigger_check_async()

    def on_open_folder(self, icon, item):
        folder = os.path.expanduser(os.getenv("LMS_STORAGE_DIR", "~/Documents/University"))
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def on_view_deadlines(self, icon, item):
        def _fetch_and_show():
            prev_state = self.current_state
            self.set_state(TrayIconTheme.STATE_WORKING, "Loading upcoming deadlines...")
            try:
                import lms_deadlines
                items = lms_deadlines.get_deadlines()
                if not items:
                    txt = "[Deadlines] LMS Upcoming Deadlines\n\nNo upcoming active deadlines found on Blackboard."
                else:
                    lines = ["[Deadlines] Upcoming LMS Deadlines\n"]
                    for i, it in enumerate(items, 1):
                        lines.append(
                            f"{i}. [Task] {it['title']}\n"
                            f"   Course: {it['course']}\n"
                            f"   Instructor: {it['doctor']}\n"
                            f"   Due: {it['due_str']} ({it['countdown']})\n"
                        )
                    txt = "\n".join(lines).strip()
                self.set_state(prev_state if prev_state != TrayIconTheme.STATE_WORKING else TrayIconTheme.STATE_SYNCED)
            except Exception as e:
                txt = f"Error loading deadlines:\n{e}"
                self.set_state(TrayIconTheme.STATE_ERROR, str(e))
            from config_gui import show_info_window
            show_info_window("Upcoming Deadlines", txt)
        threading.Thread(target=_fetch_and_show, daemon=True).start()

    def on_view_grades(self, icon, item):
        def _fetch_and_show():
            prev_state = self.current_state
            self.set_state(TrayIconTheme.STATE_WORKING, "Loading grades & feedback...")
            try:
                import lms_grades
                data = lms_grades.get_all_grades()
                lines = ["[Grades] University Academic Grades & Evaluation\n"]
                for c in data:
                    lines.append(f"{c['course']} ({c['doctor']})")
                    if not c["grades"]:
                        lines.append("   No posted grades yet.\n")
                        continue
                    for g in c["grades"]:
                        score, pos, status = g["score"], g["possible"], g["status"]
                        if score is not None and pos:
                            pct = (score / pos) * 100.0
                            grade_str = f"{score} / {pos} ({pct:.1f}%)"
                        elif score is not None:
                            grade_str = f"{score}"
                        elif status:
                            grade_str = f"{status}"
                        else:
                            grade_str = "—"
                        lines.append(f"   • {g['name']}: {grade_str}")
                        if g["feedback"]:
                            lines.append(f"     Feedback: {g['feedback']}")
                    lines.append("")
                txt = "\n".join(lines).strip()
                self.set_state(prev_state if prev_state != TrayIconTheme.STATE_WORKING else TrayIconTheme.STATE_SYNCED)
            except Exception as e:
                txt = f"Error loading grades:\n{e}"
                self.set_state(TrayIconTheme.STATE_ERROR, str(e))
            from config_gui import show_info_window
            show_info_window("Grades & Feedback", txt)
        threading.Thread(target=_fetch_and_show, daemon=True).start()

    def on_configure(self, icon, item):
        from config_gui import show_config_dialog
        threading.Thread(target=show_config_dialog, kwargs={"on_saved_callback": self.trigger_check_async}, daemon=True).start()

    def on_exit(self, icon, item):
        self.is_running = False
        if self.icon:
            self.icon.stop()

    def run(self):
        check_lms.init_config()
        if not check_lms.is_configured():
            self.current_state = TrayIconTheme.STATE_NOT_CONFIGURED
            self.last_status_message = "Missing credentials in .env"
        else:
            self.current_state = TrayIconTheme.STATE_SYNCED

        initial_image = self.theme.get_image(self.current_state)

        menu = pystray.Menu(
            pystray.MenuItem("Open Course Folder", self.on_open_folder, default=True),
            pystray.MenuItem("Check Now", self.on_check_now),
            pystray.MenuItem("Upcoming Deadlines", self.on_view_deadlines),
            pystray.MenuItem("Grades & Feedback", self.on_view_grades),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Configure Settings", self.on_configure),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.on_exit)
        )

        self.icon = pystray.Icon(
            "BlackboardSentinel",
            initial_image,
            self.get_tooltip(),
            menu
        )

        # Start animation and scheduler threads
        self._anim_thread = threading.Thread(target=self.animation_loop, daemon=True)
        self._anim_thread.start()

        self._check_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self._check_thread.start()

        # Run pystray main loop
        self.icon.run()


def close_other_instances():
    """Close any older background instances so only the current updated instance runs."""
    if sys.platform == "win32":
        try:
            my_pid = os.getpid()
            ps_cmd = f"Get-Process -Name 'BlackboardSentinel' -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -ne {my_pid} }} | Stop-Process -Force -ErrorAction SilentlyContinue"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass


def main():
    check_lms.init_config()
    force_setup = "--setup" in sys.argv or "--configure" in sys.argv or "-s" in sys.argv
    if not check_lms.is_configured() or force_setup:
        close_other_instances()
        from config_gui import show_config_dialog
        saved = show_config_dialog()
        if not saved and not check_lms.is_configured():
            return
        check_lms.init_config()

    close_other_instances()
    app = SentinelTrayApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            import tkinter.messagebox as mb
            mb.showerror("Blackboard Sentinel", f"An unexpected error occurred:\n{e}")
        except Exception:
            pass
