import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestSyntaxAndStaticChecks(unittest.TestCase):
    def test_python_310_compatible_fstrings_in_lms_grades(self):
        src = (REPO_ROOT / "lms_grades.py").read_text(encoding="utf-8")
        ast.parse(src, filename="lms_grades.py")
        # Line 43 previously had nested double quotes inside f-string
        for i, line in enumerate(src.splitlines(), 1):
            if 'f"' in line:
                # Extract {...} expressions and ensure no unescaped double quotes inside
                in_expr = False
                depth = 0
                for ch in line[line.index('f"') + 2:]:
                    if ch == "{":
                        depth += 1
                        in_expr = True
                    elif ch == "}" and depth > 0:
                        depth -= 1
                        if depth == 0:
                            in_expr = False
                    elif ch == '"' and in_expr:
                        self.fail(f"Nested double quote in f-string at lms_grades.py:{i}: {line}")

    def test_lms_deadlines_uses_check_lms_state_file(self):
        src = (REPO_ROOT / "lms_deadlines.py").read_text(encoding="utf-8")
        self.assertIn("check_lms.STATE_FILE", src)
        self.assertNotIn('os.path.expanduser("~/.hermes/state/lms_tracker_state.json")', src)


class TestTrayAppLazyImportAndMainThread(unittest.TestCase):
    def test_pystray_not_imported_on_module_load(self):
        code = (
            "import sys; sys.path.insert(0, %r); "
            "import tray_app; "
            "assert 'pystray' not in sys.modules, 'pystray was eagerly imported!'"
        ) % str(REPO_ROOT)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_hide_dock_icon_uses_shared_application(self):
        import tray_app
        mock_app = mock.MagicMock()
        with mock.patch("AppKit.NSApplication") as mock_nsapp_cls:
            mock_nsapp_cls.sharedApplication.return_value = mock_app
            tray_app.hide_dock_icon_macos()
            mock_nsapp_cls.sharedApplication.assert_called_once()
            mock_app.setActivationPolicy_.assert_called_once()

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_run_on_main_thread_uses_apphelper_off_main_thread(self):
        import tray_app
        called = []

        def worker():
            tray_app._run_on_main_thread(lambda: called.append("ran"))

        with mock.patch("PyObjCTools.AppHelper.callAfter") as mock_call_after:
            t = threading.Thread(target=worker)
            t.start()
            t.join()
            mock_call_after.assert_called_once()

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_set_state_and_animation_dispatch_via_main_thread(self):
        import tray_app
        app = tray_app.SentinelTrayApp()
        app.icon = mock.MagicMock()

        dispatched = []

        def fake_run_on_main(fn):
            dispatched.append(threading.current_thread() is threading.main_thread())
            fn()

        with mock.patch.object(tray_app, "_run_on_main_thread", side_effect=fake_run_on_main):
            def bg():
                app.set_state("working", "Testing")
                img = app.theme.get_image("working", 0.1)
                app._schedule_icon_image(img)

            t = threading.Thread(target=bg)
            t.start()
            t.join()

        self.assertEqual(len(dispatched), 2)
        self.assertFalse(any(dispatched))

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_run_passes_setup_callback_to_pystray(self):
        import tray_app
        app = tray_app.SentinelTrayApp()
        fake_icon = mock.MagicMock()

        def fake_run(setup=None):
            self.assertIsNotNone(setup)
            # Simulate pystray calling setup from background thread
            t = threading.Thread(target=lambda: setup(fake_icon))
            t.start()
            t.join()
            app.is_running = False

        fake_icon.run.side_effect = fake_run

        with mock.patch("pystray.Icon", return_value=fake_icon), \
             mock.patch("pystray.Menu"), \
             mock.patch("pystray.MenuItem"), \
             mock.patch.object(tray_app, "_run_on_main_thread", side_effect=lambda fn: fn()), \
             mock.patch.object(app, "animation_loop"), \
             mock.patch.object(app, "scheduler_loop"):
            app.run()

        self.assertTrue(fake_icon.visible)


class TestSingleInstanceAndNotifications(unittest.TestCase):
    def test_is_tray_process_cmd_excludes_dialog_helpers(self):
        import tray_app
        self.assertTrue(tray_app._is_tray_process_cmd("/path/to/python /repo/tray_app.py"))
        self.assertTrue(tray_app._is_tray_process_cmd("/Applications/BlackboardSentinel.app/Contents/MacOS/BlackboardSentinel"))
        self.assertFalse(tray_app._is_tray_process_cmd("/path/to/python /repo/tray_app.py --config-dialog"))
        self.assertFalse(tray_app._is_tray_process_cmd("/Applications/BlackboardSentinel.app/Contents/MacOS/BlackboardSentinel --info-dialog"))
        self.assertFalse(tray_app._is_tray_process_cmd("zsh -c 'echo tray_app.py'"))

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_no_duplicate_macos_notifications(self):
        import tray_app
        import check_lms

        app = tray_app.SentinelTrayApp()
        app.icon = mock.MagicMock()

        with mock.patch.object(check_lms, "init_config"), \
             mock.patch.object(check_lms, "is_configured", return_value=True), \
             mock.patch.object(check_lms, "load_state", return_value={}), \
             mock.patch.object(check_lms, "save_state"), \
             mock.patch.object(check_lms, "LMSClient") as mock_client_cls, \
             mock.patch.object(check_lms, "get_courses_map", return_value={}), \
             mock.patch.object(check_lms, "sync_all_courses", return_value=(["file1"], [], [], [])), \
             mock.patch.object(check_lms, "check_grades", return_value=[]), \
             mock.patch.object(check_lms, "check_deadlines", return_value=[]), \
             mock.patch.object(check_lms, "format_update_messages", return_value=["1 new file"]), \
             mock.patch.object(check_lms, "send_notification") as mock_send_notif, \
             mock.patch.object(app, "set_state"):
            mock_client_cls.return_value.login.return_value = True
            app._run_check_worker()

        mock_send_notif.assert_called_once()
        app.icon.notify.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_dialogs_spawn_subprocesses_on_macos(self):
        import tray_app
        app = tray_app.SentinelTrayApp()

        with mock.patch("subprocess.run") as mock_sub_run:
            app._show_info_dialog("Test Title", "Hello World")
            mock_sub_run.assert_called_once()
            cmd = mock_sub_run.call_args[0][0]
            self.assertIn("--info-dialog", cmd)
            payload = json.loads(mock_sub_run.call_args.kwargs["input"])
            self.assertEqual(payload, {"title": "Test Title", "content": "Hello World"})

        fake_proc = mock.MagicMock()
        fake_proc.wait.return_value = 2
        with mock.patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            app.on_configure(None, None)
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            self.assertIn("--config-dialog", cmd)


class TestTrayIconTheme(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_theme_uses_nsuserdefaults_with_ttl_cache_no_subprocess(self):
        import AppKit
        import tray_icon
        tray_icon._DARWIN_THEME_CACHE["ts"] = 0.0

        mock_ud = mock.MagicMock()
        mock_ud.stringForKey_.return_value = "Dark"

        with mock.patch.object(AppKit, "NSApp", None), \
             mock.patch("Foundation.NSUserDefaults") as mock_nsud_cls, \
             mock.patch("subprocess.run", side_effect=AssertionError("subprocess should not be called")):
            mock_nsud_cls.standardUserDefaults.return_value = mock_ud
            res1 = tray_icon.is_system_taskbar_light()
            res2 = tray_icon.is_system_taskbar_light()

        self.assertFalse(res1)
        self.assertFalse(res2)
        # Second call within TTL hits cache without calling NSUserDefaults again
        self.assertEqual(mock_ud.stringForKey_.call_count, 1)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_theme_uses_nsapp_effective_appearance_for_auto_dark_mode(self):
        import AppKit
        import tray_icon
        tray_icon._DARWIN_THEME_CACHE["ts"] = 0.0

        mock_appearance = mock.MagicMock()
        mock_appearance.bestMatchFromAppearancesWithNames_.return_value = AppKit.NSAppearanceNameDarkAqua
        mock_nsapp = mock.MagicMock()
        mock_nsapp.effectiveAppearance.return_value = mock_appearance

        with mock.patch.object(AppKit, "NSApp", mock_nsapp), \
             mock.patch("subprocess.run", side_effect=AssertionError("subprocess should not be called")):
            self.assertFalse(tray_icon.is_system_taskbar_light())


class TestConfigAndInitOverride(unittest.TestCase):
    def test_init_config_override_reloads_env(self):
        import check_lms
        with tempfile.TemporaryDirectory() as tmp:
            env_path = pathlib.Path(tmp) / ".env"
            env_path.write_text('LMS_URL="https://first.example.edu"\nLMS_USER_ID="u1"\n', encoding="utf-8")
            old_cwd = os.getcwd()
            old_url = os.environ.get("LMS_URL")
            old_uid = os.environ.get("LMS_USER_ID")
            try:
                os.chdir(tmp)
                os.environ.pop("LMS_URL", None)
                os.environ.pop("LMS_USER_ID", None)
                with mock.patch.object(check_lms, "get_keyring_password", return_value=""), \
                     mock.patch.object(check_lms, "set_keyring_password", return_value=True):
                    check_lms.init_config()
                    self.assertEqual(check_lms.LMS_URL, "https://first.example.edu")

                    env_path.write_text('LMS_URL="https://second.example.edu"\nLMS_USER_ID="u2"\n', encoding="utf-8")
                    check_lms.init_config(override=False)
                    self.assertEqual(check_lms.LMS_URL, "https://first.example.edu")

                    check_lms.init_config(override=True)
                    self.assertEqual(check_lms.LMS_URL, "https://second.example.edu")
                    self.assertEqual(check_lms.USER_ID, "u2")
            finally:
                os.chdir(old_cwd)
                if old_url is None:
                    os.environ.pop("LMS_URL", None)
                else:
                    os.environ["LMS_URL"] = old_url
                if old_uid is None:
                    os.environ.pop("LMS_USER_ID", None)
                else:
                    os.environ["LMS_USER_ID"] = old_uid
                check_lms.init_config(override=True)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_make_button_returns_ttk_on_macos(self):
        code = (
            "import sys, tkinter as tk; from tkinter import ttk; "
            "sys.path.insert(0, %r); import config_gui; "
            "root = tk.Tk(); btn = config_gui._make_button(root, 'Apply', primary=True); "
            "assert isinstance(btn, ttk.Button); root.destroy()"
        ) % str(REPO_ROOT)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_frozen_config_paths_skip_bundle_dir(self):
        import config_gui
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch("os.getcwd", return_value="/tmp/some_other_cwd"), \
             mock.patch.object(config_gui, "get_default_config_path", return_value="/tmp/nonexistent_sentinel_test/.env"), \
             mock.patch("os.path.isfile", return_value=False) as mock_isfile:
            config_gui.load_existing_config()
            checked = [c.args[0] for c in mock_isfile.call_args_list]
            bundle_env = os.path.join(os.path.dirname(os.path.abspath(config_gui.__file__)), ".env")
            self.assertNotIn(bundle_env, checked)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_mousewheel_scroll_handles_macos_small_delta(self):
        code = "\n".join([
            "import tkinter as tk",
            "from unittest import mock",
            "root = tk.Tk()",
            "canvas = tk.Canvas(root)",
            "ev = mock.MagicMock(delta=1)",
            "units = int(-ev.delta) or (-1 if ev.delta > 0 else 1)",
            "with mock.patch.object(canvas, 'yview_scroll') as ms:",
            "    canvas.yview_scroll(units, 'units')",
            "    ms.assert_called_with(-1, 'units')",
            "root.destroy()",
        ])
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_passwordless_sso_detected_as_settings_mode(self):
        import check_lms
        import config_gui
        with mock.patch.object(config_gui, "load_existing_config", return_value={
            "LMS_URL": "https://lms.example.edu",
            "LMS_USER_ID": "",
            "LMS_PASSWORD": "",
            "LMS_STORAGE_DIR": "~/Documents/University",
            "LMS_COURSES": "",
            "TRAY_THEME": "auto",
            "LMS_KEEP_ALL_ANNOUNCEMENTS": "false",
            "LMS_HERMES_MESSAGING": "false",
            "LMS_EXPAND_ZIPS": "false",
            "LMS_DELETE_ORIGINAL_ZIP": "false",
            "LMS_MAX_FILE_SIZE_MB": "0",
        }), mock.patch.object(check_lms, "has_valid_browser_session", return_value=True):
            if sys.platform == "darwin":
                import config_gui_mac
                fake_appkit = mock.MagicMock()
                fake_win = fake_appkit.NSWindow.alloc.return_value.initWithContentRect_styleMask_backing_defer_.return_value
                with mock.patch.object(config_gui_mac, "AppKit", fake_appkit), \
                     mock.patch.object(config_gui_mac, "FlippedView", fake_appkit.NSView), \
                     mock.patch.object(config_gui_mac, "_ConfigController", mock.MagicMock()), \
                     mock.patch.object(config_gui_mac, "_install_standard_menus"), \
                     mock.patch.object(config_gui_mac, "_load_app_icon", return_value=None):
                    config_gui.show_config_dialog()
                    fake_win.setTitle_.assert_called_with("Blackboard Sentinel - Settings")
            else:
                titles = []
                fake_root = mock.MagicMock()
                fake_root.title.side_effect = lambda t: titles.append(t)
                fake_root.mainloop.side_effect = lambda: None
                with mock.patch("tkinter.Tk", return_value=fake_root), \
                     mock.patch("tkinter.StringVar"), \
                     mock.patch("tkinter.BooleanVar"), \
                     mock.patch("tkinter.Frame"), \
                     mock.patch("tkinter.Label"), \
                     mock.patch("tkinter.Canvas"), \
                     mock.patch("tkinter.Checkbutton"), \
                     mock.patch("tkinter.ttk.Entry"), \
                     mock.patch("tkinter.ttk.Button"), \
                     mock.patch("tkinter.ttk.Combobox"), \
                     mock.patch("tkinter.ttk.Checkbutton"), \
                     mock.patch("tkinter.ttk.Scrollbar"), \
                     mock.patch("tkinter.PhotoImage"):
                    config_gui.show_config_dialog()
                self.assertIn("Blackboard Sentinel - Settings", titles)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_activate_regular_app_runs_after_tk_init(self):
        import config_gui
        # Verify macOS delegates to AppKit config_gui_mac and Tk fallback still orders tk before _activate
        with mock.patch("config_gui_mac.show_info_window_mac") as mock_mac_info:
            config_gui.show_info_window("Title", "Body")
            mock_mac_info.assert_called_once_with("Title", "Body")

        call_order = []
        fake_root = mock.MagicMock()
        fake_root.mainloop.side_effect = lambda: None
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch("tkinter.Tk", side_effect=lambda: (call_order.append("tk"), fake_root)[1]), \
             mock.patch.object(config_gui, "_activate_macos_regular_app", side_effect=lambda: call_order.append("activate")), \
             mock.patch("tkinter.Frame"), \
             mock.patch("tkinter.Label"), \
             mock.patch("tkinter.Text"), \
             mock.patch("tkinter.ttk.Scrollbar"), \
             mock.patch("tkinter.ttk.Button"), \
             mock.patch("tkinter.PhotoImage"):
            config_gui.show_info_window("Title", "Body")
        self.assertGreaterEqual(len(call_order), 2)
        self.assertEqual(call_order[0], "tk")
        self.assertEqual(call_order[1], "activate")

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific test")
    def test_get_ssl_context_falls_back_to_etc_ssl_cert_pem(self):
        import ssl
        import check_lms
        fake_paths = mock.MagicMock(cafile=None, openssl_cafile="/nonexistent/cert.pem")
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("ssl.get_default_verify_paths", return_value=fake_paths), \
             mock.patch("ssl.create_default_context") as mock_ctx:
            os.environ.pop("SSL_CERT_FILE", None)
            check_lms._get_ssl_context()
            mock_ctx.assert_called_once_with(cafile="/etc/ssl/cert.pem")

    def test_get_paginated_json_follows_next_page(self):
        import check_lms
        client = check_lms.LMSClient("u", "p")
        pages = {
            "/learn/api/public/v1/courses/c1/announcements": {
                "results": [{"id": "a1"}],
                "paging": {"nextPage": "/learn/api/public/v1/courses/c1/announcements?offset=10"},
            },
            "/learn/api/public/v1/courses/c1/announcements?offset=10": {
                "results": [{"id": "a2"}],
            },
        }
        with mock.patch.object(client, "get_json", side_effect=lambda ep, timeout=None: pages.get(ep)):
            res = client.get_paginated_json("/learn/api/public/v1/courses/c1/announcements")
        self.assertEqual([r["id"] for r in res["results"]], ["a1", "a2"])

    def test_write_web_shortcut_macos_webloc_and_url_elsewhere(self):
        import plistlib
        import check_lms
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sys, "platform", "darwin"):
                p_mac = check_lms._write_web_shortcut(tmp, "Course Survey", "https://gate.ut.edu.sa/?a=1&b=2")
                self.assertTrue(p_mac.endswith(".webloc"))
                with open(p_mac, "rb") as f:
                    parsed = plistlib.load(f)
                self.assertEqual(parsed["URL"], "https://gate.ut.edu.sa/?a=1&b=2")
            with mock.patch.object(sys, "platform", "win32"):
                p_win = check_lms._write_web_shortcut(tmp, "Course Survey", "https://gate.ut.edu.sa/?a=1&b=2")
                self.assertTrue(p_win.endswith(".url"))
                self.assertIn("URL=https://gate.ut.edu.sa/?a=1&b=2", pathlib.Path(p_win).read_text(encoding="utf-8"))

    def test_hermes_messaging_defaults_off_and_loads_hermes_env_fallback(self):
        import check_lms
        import config_gui
        with tempfile.TemporaryDirectory() as tmp:
            hermes_env = os.path.join(tmp, ".env")
            with open(hermes_env, "w", encoding="utf-8") as f:
                f.write('LMS_URL="https://lms.ut.edu.sa"\nLMS_USER_ID="481000670"\n')
            with mock.patch.object(config_gui, "get_default_config_path", return_value=os.path.join(tmp, "missing.env")), \
                 mock.patch("os.getcwd", return_value=tmp + "_empty"), \
                 mock.patch("os.path.expanduser", side_effect=lambda p: hermes_env if p == "~/.hermes/.env" else p), \
                 mock.patch.object(check_lms, "get_keyring_password", return_value=""):
                cfg = config_gui.load_existing_config()
            self.assertEqual(cfg["LMS_URL"], "https://lms.ut.edu.sa")
            self.assertEqual(cfg["LMS_HERMES_MESSAGING"], "false")

    def test_get_courses_map_respects_custom_storage_dir(self):
        import check_lms
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "Documents")
            os.makedirs(os.path.join(docs_dir, "AI FUNDAMENTALS"), exist_ok=True)
            custom_storage = os.path.join(docs_dir, "university_test")
            os.makedirs(custom_storage, exist_ok=True)

            fake_client = mock.MagicMock()
            fake_client.get_paginated_json.return_value = {"results": [{"courseId": "_c1_1"}]}
            fake_client.get_json.return_value = {"name": "AI Fundamentals 601 CSC"}

            old_storage = check_lms.LMS_STORAGE_DIR
            try:
                check_lms.LMS_STORAGE_DIR = custom_storage
                with mock.patch.dict(os.environ, {"LMS_COURSES": ""}, clear=False), \
                     mock.patch("os.path.expanduser", side_effect=lambda p: docs_dir if p == "~/Documents" else os.path.join(docs_dir, "University") if p == "~/Documents/University" else p):
                    cmap = check_lms.get_courses_map(fake_client)
            finally:
                check_lms.LMS_STORAGE_DIR = old_storage

            self.assertEqual(
                cmap["_c1_1"]["dir"],
                os.path.join(custom_storage, "AI Fundamentals 601 CSC"),
            )


if __name__ == "__main__":
    unittest.main()
