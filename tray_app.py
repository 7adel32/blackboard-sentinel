"""
Blackboard Sentinel - System Tray / Menu Bar Resident Application
Supports state-driven tinting, real-time animation, scheduled background checks,
and native desktop notifications.
"""

import json
import os
import signal
import sys
import time
import threading
import subprocess
from datetime import datetime

def _run_info_dialog_helper():
    title = "Blackboard Sentinel"
    content = ""
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            title = data.get("title", title)
            content = data.get("content", "")
    except Exception as e:
        content = f"Unable to display dialog content: {e}"
    from config_gui import show_info_window
    show_info_window(title, content)
    return 0


if __name__ == "__main__" and "--info-dialog" in sys.argv:
    sys.exit(_run_info_dialog_helper())

import check_lms
from tray_icon import TrayIconTheme


def _run_on_main_thread(fn):
    """Execute fn on the main thread (via PyObjCTools.AppHelper.callAfter on macOS)."""
    if sys.platform == "darwin" and threading.current_thread() is not threading.main_thread():
        try:
            from PyObjCTools import AppHelper
            AppHelper.callAfter(fn)
            return
        except Exception:
            pass
    fn()


def _build_self_command(*args):
    """Build argv list to re-invoke this script or frozen bundle executable."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, os.path.abspath(__file__), *args]


def get_pid_file_path():
    """Return path to the single-instance PID file for the resident tray process."""
    if sys.platform == "darwin":
        base_dir = os.path.expanduser("~/Library/Application Support/BlackboardSentinel")
    elif sys.platform == "win32":
        appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
        base_dir = os.path.join(appdata, "BlackboardSentinel")
    else:
        base_dir = os.path.expanduser("~/.blackboard-sentinel")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "tray_app.pid")


def write_pid_file():
    try:
        with open(get_pid_file_path(), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def remove_pid_file():
    try:
        pid_path = get_pid_file_path()
        if os.path.isfile(pid_path):
            with open(pid_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content == str(os.getpid()):
                os.remove(pid_path)
    except Exception:
        pass


def hide_dock_icon_macos():
    """On macOS, set activation policy to accessory so the app runs purely in the menu bar without a Dock icon."""
    if sys.platform == "darwin":
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass


def set_activation_policy_regular_macos():
    """On macOS, promote helper dialog process to a regular foreground app so windows focus and accept input."""
    if sys.platform == "darwin":
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyRegular
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            app.activateIgnoringOtherApps_(True)
        except Exception:
            pass


def _terminate_pid_macos(pid, timeout=2.0):
    """Gracefully terminate a macOS process, escalating to SIGKILL if needed."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        return

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except Exception:
            break
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


def _is_dialog_helper_cmd(cmd):
    return "--config-dialog" in cmd or "--info-dialog" in cmd


def _is_tray_process_cmd(cmd):
    if not cmd or _is_dialog_helper_cmd(cmd):
        return False
    if "BlackboardSentinel.app/Contents/MacOS/BlackboardSentinel" in cmd:
        return True
    tokens = cmd.split()
    return any(os.path.basename(tok) == "tray_app.py" for tok in tokens)


def close_other_instances():
    """Close any older background tray instances without killing dialog helper subprocesses."""
    my_pid = os.getpid()
    parent_pid = os.getppid()
    if sys.platform == "win32":
        try:
            ps_cmd = (
                f"Get-Process -Name 'BlackboardSentinel' -ErrorAction SilentlyContinue | "
                f"Where-Object {{ $_.Id -ne {my_pid} }} | Stop-Process -Force -ErrorAction SilentlyContinue"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
    elif sys.platform == "darwin":
        killed_pids = set()
        # 1. Check PID file first
        try:
            pid_path = get_pid_file_path()
            if os.path.isfile(pid_path):
                with open(pid_path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                if raw.isdigit():
                    old_pid = int(raw)
                    if old_pid not in (my_pid, parent_pid):
                        ps_check = subprocess.run(
                            ["ps", "-p", str(old_pid), "-o", "command="],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        cmd = ps_check.stdout.strip()
                        if cmd and not _is_dialog_helper_cmd(cmd) and (
                            "tray_app.py" in cmd or "BlackboardSentinel" in cmd
                        ):
                            _terminate_pid_macos(old_pid)
                            killed_pids.add(old_pid)
        except Exception:
            pass

        # 2. Scan active processes for any older tray instances (frozen .app or tray_app.py)
        try:
            ps_out = subprocess.run(
                ["ps", "-ax", "-o", "pid=,command="],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.splitlines()
            for line in ps_out:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) < 2 or not parts[0].isdigit():
                    continue
                p = int(parts[0])
                cmd = parts[1]
                if p in (my_pid, parent_pid) or p in killed_pids:
                    continue
                if _is_tray_process_cmd(cmd):
                    _terminate_pid_macos(p)
                    killed_pids.add(p)
        except Exception:
            pass


class SentinelTrayApp:
    def __init__(self, check_interval_minutes=60):
        self.check_interval_seconds = max(10, check_interval_minutes) * 60  # never poll more often than every 10 minutes
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
        self._anim_lock = threading.Lock()
        self._pending_anim_image = None
        self._anim_dispatch_pending = False
        self._config_proc = None
        self._config_lock = threading.Lock()
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

    def _schedule_icon_image(self, image):
        if not self.is_running or not self.icon:
            return
        if sys.platform == "darwin" and threading.current_thread() is not threading.main_thread():
            with self._anim_lock:
                self._pending_anim_image = image
                if self._anim_dispatch_pending:
                    return
                self._anim_dispatch_pending = True

            def _flush():
                with self._anim_lock:
                    img = self._pending_anim_image
                    self._pending_anim_image = None
                    self._anim_dispatch_pending = False
                if img is not None and self.is_running and self.icon:
                    self.icon.icon = img

            _run_on_main_thread(_flush)
        else:
            self.icon.icon = image

    def set_state(self, state, message=""):
        self.current_state = state
        self.state_start_time = time.time()
        if message:
            self.last_status_message = message
        if self.icon:
            tooltip = self.get_tooltip()
            image = self.theme.get_image(self.current_state, 0.0)

            def _apply():
                if self.icon and self.is_running:
                    self.icon.title = tooltip
                    self.icon.icon = image

            _run_on_main_thread(_apply)

    def animation_loop(self):
        """Dedicated loop updating tray icon during dynamic animated states."""
        while self.is_running:
            if not self.icon:
                time.sleep(0.1)
                continue

            elapsed = time.time() - self.state_start_time

            if self.current_state == TrayIconTheme.STATE_WORKING:
                # Continuous pulsing while actively checking
                img = self.theme.get_image(self.current_state, elapsed)
                self._schedule_icon_image(img)
                time.sleep(0.06)

            elif self.current_state == TrayIconTheme.STATE_ERROR:
                # Continuous pulsing breathing animation in error state
                img = self.theme.get_image(self.current_state, elapsed)
                self._schedule_icon_image(img)
                time.sleep(0.06)

            elif self.current_state == TrayIconTheme.STATE_NEW_NOTIFICATION:
                if elapsed <= 1.0:
                    # 1-second pulse animation
                    img = self.theme.get_image(self.current_state, elapsed)
                    self._schedule_icon_image(img)
                    time.sleep(0.05)
                else:
                    # Animation finished: return to synced state
                    self.set_state(TrayIconTheme.STATE_SYNCED)
                    time.sleep(0.1)

            else:
                # Static states (synced, not_configured) sleep gently
                time.sleep(0.3)

    def trigger_check_async(self):
        if self.is_checking:
            return
        threading.Thread(target=self._run_check_worker, daemon=True).start()

    def _run_check_worker(self):
        self.is_checking = True
        self.set_state(TrayIconTheme.STATE_WORKING, "Syncing courses and grades...")

        check_lms.init_config(override=True)
        if not check_lms.is_configured():
            self.set_state(TrayIconTheme.STATE_NOT_CONFIGURED, "Credentials missing in .env")
            self.is_checking = False
            return

        try:
            state = check_lms.load_state()
            client = check_lms.LMSClient(check_lms.USER_ID, check_lms.PASSWORD)
            client.login()

            courses_dict = check_lms.get_courses_map(client)
            all_downloads, all_new_requests, all_announcements, all_external_links = check_lms.sync_all_courses(
                client, state, courses_dict
            )

            all_grades = check_lms.check_grades(client, state, courses_map=courses_dict)
            all_deadlines = check_lms.check_deadlines(client, state, courses_map=courses_dict)
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
                    all_external_links=all_external_links,
                )

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

                if messages:
                    combined_text = "\n\n---\n\n".join(messages).strip()
                    check_lms.send_notification(combined_text, "Blackboard Sentinel")
                    # On macOS, send_notification already invokes send_macos_notification;
                    # skip pystray's icon.notify to avoid duplicate macOS notifications.
                    if sys.platform != "darwin" and self.icon:
                        try:
                            self.icon.notify(summary_text, "Blackboard Sentinel")
                        except Exception:
                            if sys.platform == "win32":
                                check_lms.send_windows_toast("Blackboard Sentinel", summary_text)
                else:
                    if sys.platform == "darwin":
                        check_lms.send_macos_notification("Blackboard Sentinel", summary_text)
                    elif self.icon:
                        try:
                            self.icon.notify(summary_text, "Blackboard Sentinel")
                        except Exception:
                            if sys.platform == "win32":
                                check_lms.send_windows_toast("Blackboard Sentinel", summary_text)
            else:
                self.set_state(TrayIconTheme.STATE_SYNCED, "All courses up to date")

        except Exception as e:
            self.set_state(TrayIconTheme.STATE_ERROR, str(e))
        finally:
            self.is_checking = False

    def run_cached_reminders(self):
        """Evaluate deadline reminders from the local cache (no network, no login)."""
        if self.is_checking:
            return
        try:
            state = check_lms.load_state()
            alerts = check_lms.check_cached_reminders(state)
            if not alerts:
                return
            check_lms.save_state(state)
            messages = check_lms.format_update_messages([], [], [], [], alerts, [])
            if messages:
                check_lms.send_notification("\n\n---\n\n".join(messages).strip(), "Blackboard Sentinel")
        except Exception:
            pass

    def scheduler_loop(self):
        """Background thread executing periodic checks plus cheap offline deadline reminders."""
        # Initial check after 5 seconds of launch
        time.sleep(5)
        reminder_interval = 3600  # seconds; offline, only reads the local state file
        while self.is_running:
            self.trigger_check_async()
            # Wait for next interval in small slices to respond quickly to shutdown
            elapsed = 0
            while elapsed < self.check_interval_seconds:
                if not self.is_running:
                    return
                time.sleep(2)
                elapsed += 2
                if elapsed % reminder_interval == 0:
                    self.run_cached_reminders()

    def _show_info_dialog(self, title, content):
        """Display an info window safely (helper subprocess on macOS to avoid Tk+pystray conflict)."""
        if sys.platform == "darwin":
            payload = json.dumps({"title": title, "content": content}, ensure_ascii=False)
            subprocess.run(
                _build_self_command("--info-dialog"),
                input=payload,
                text=True,
                check=False,
            )
        else:
            from config_gui import show_info_window
            show_info_window(title, content)

    # Context Menu Actions
    def on_check_now(self, icon, item):
        self.trigger_check_async()

    def on_open_folder(self, icon, item):
        folder = os.path.expanduser(os.getenv("LMS_STORAGE_DIR", "~/Documents/University"))
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
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
                            f"   Status: {it['submission']}\n"
                        )
                    txt = "\n".join(lines).strip()
                self.set_state(prev_state if prev_state != TrayIconTheme.STATE_WORKING else TrayIconTheme.STATE_SYNCED)
            except Exception as e:
                txt = f"Error loading deadlines:\n{e}"
                self.set_state(TrayIconTheme.STATE_ERROR, str(e))
            self._show_info_dialog("Upcoming Deadlines", txt)

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
            self._show_info_dialog("Grades & Feedback", txt)

        threading.Thread(target=_fetch_and_show, daemon=True).start()

    def on_configure(self, icon, item):
        if sys.platform == "darwin":
            with self._config_lock:
                if self._config_proc is not None and self._config_proc.poll() is None:
                    try:
                        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
                        running_app = NSRunningApplication.runningApplicationWithProcessIdentifier_(self._config_proc.pid)
                        if running_app is not None:
                            running_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                    except Exception:
                        pass
                    return
                proc = subprocess.Popen(_build_self_command("--config-dialog"))
                self._config_proc = proc

            def _wait_for_config():
                rc = proc.wait()
                with self._config_lock:
                    if self._config_proc is proc:
                        self._config_proc = None
                if rc == 0 and self.is_running:
                    check_lms.init_config(override=True)
                    self.trigger_check_async()

            threading.Thread(target=_wait_for_config, daemon=True).start()
        else:
            from config_gui import show_config_dialog
            threading.Thread(
                target=show_config_dialog,
                kwargs={"on_saved_callback": self.trigger_check_async},
                daemon=True,
            ).start()

    def on_exit(self, icon, item):
        self.is_running = False
        if self.icon:
            _run_on_main_thread(self.icon.stop)

    def run(self):
        import pystray

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
            pystray.MenuItem("Exit", self.on_exit),
        )

        self.icon = pystray.Icon(
            "BlackboardSentinel",
            initial_image,
            self.get_tooltip(),
            menu,
        )

        def _setup(icon):
            def _show():
                if self.is_running:
                    icon.visible = True

            _run_on_main_thread(_show)
            self._anim_thread = threading.Thread(target=self.animation_loop, daemon=True)
            self._anim_thread.start()
            self._check_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
            self._check_thread.start()

        write_pid_file()
        try:
            self.icon.run(setup=_setup)
        finally:
            self.is_running = False
            remove_pid_file()


def _run_config_dialog_helper():
    from config_gui import show_config_dialog
    saved = show_config_dialog()
    return 0 if saved else 2


def main():
    if "--config-dialog" in sys.argv:
        sys.exit(_run_config_dialog_helper())
    if "--info-dialog" in sys.argv:
        sys.exit(_run_info_dialog_helper())

    check_lms.init_config()
    force_setup = "--setup" in sys.argv or "--configure" in sys.argv or "-s" in sys.argv
    if not check_lms.is_configured() or force_setup:
        close_other_instances()
        if sys.platform == "darwin":
            proc = subprocess.run(_build_self_command("--config-dialog"), check=False)
            check_lms.init_config(override=True)
            if proc.returncode != 0 and not check_lms.is_configured():
                return
        else:
            from config_gui import show_config_dialog
            saved = show_config_dialog()
            if not saved and not check_lms.is_configured():
                return
            check_lms.init_config(override=True)

    close_other_instances()
    hide_dock_icon_macos()
    app = SentinelTrayApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        if sys.platform != "darwin":
            try:
                import tkinter.messagebox as mb
                mb.showerror("Blackboard Sentinel", f"An unexpected error occurred:\n{e}")
            except Exception:
                pass
        sys.exit(1)
