import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestWindowsTrayApp(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_close_other_instances_excludes_parent_pid_and_uses_no_window(self):
        import tray_app

        with mock.patch("os.getpid", return_value=2222), \
             mock.patch("os.getppid", return_value=1111), \
             mock.patch("subprocess.run") as mock_run:
            tray_app.close_other_instances()

        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], "powershell")
        ps_cmd = cmd[-1]
        self.assertIn("2222", ps_cmd)
        self.assertIn("1111", ps_cmd)
        self.assertIn("--(config|info)-dialog", ps_cmd)
        self.assertEqual(mock_run.call_args.kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
        self.assertEqual(mock_run.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_dialogs_open_inline_without_subprocess_on_win32(self):
        import config_gui
        import tray_app

        app = tray_app.SentinelTrayApp()
        with mock.patch("subprocess.run", side_effect=AssertionError("subprocess.run should not be called")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess.Popen should not be called")), \
             mock.patch.object(config_gui, "show_info_window") as mock_info:
            app._show_info_dialog("Deadlines", "Item 1")
            mock_info.assert_called_once_with("Deadlines", "Item 1")

        started = []

        class FakeThread:
            def __init__(self, target=None, kwargs=None, daemon=None):
                self._target = target
                self._kwargs = kwargs or {}

            def start(self):
                started.append((self._target, self._kwargs))

        with mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess.Popen should not be called")), \
             mock.patch("threading.Thread", side_effect=FakeThread), \
             mock.patch.object(config_gui, "show_config_dialog") as mock_cfg:
            app.on_configure(None, None)
            self.assertEqual(len(started), 1)
            self.assertIs(started[0][0], mock_cfg)

    def test_on_open_folder_handles_empty_storage_env(self):
        import tray_app

        app = tray_app.SentinelTrayApp()
        with tempfile.TemporaryDirectory() as tmp:
            fallback = os.path.join(tmp, "Documents", "University")
            with mock.patch.dict(os.environ, {"LMS_STORAGE_DIR": ""}, clear=False), \
                 mock.patch("os.path.expanduser", return_value=fallback), \
                 mock.patch("os.startfile", create=True) as mock_startfile:
                if sys.platform == "win32":
                    app.on_open_folder(None, None)
                    mock_startfile.assert_called_once_with(fallback)
                else:
                    with mock.patch("subprocess.run") as mock_run:
                        app.on_open_folder(None, None)
                        mock_run.assert_called_once()
            self.assertTrue(os.path.isdir(fallback))


class TestWindowsConfigAndSpec(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_make_button_returns_tk_button_on_win32(self):
        import tkinter as tk
        from tkinter import ttk
        import config_gui

        fake_parent = mock.MagicMock()
        with mock.patch("tkinter.Button", return_value="tk_btn") as mock_tk_btn, \
             mock.patch("tkinter.ttk.Button", side_effect=AssertionError("ttk.Button should not be used on win32")):
            btn = config_gui._make_button(fake_parent, "Apply Settings", primary=True, bg="#2563EB", fg="#FFFFFF")
        self.assertEqual(btn, "tk_btn")
        mock_tk_btn.assert_called_once()
        self.assertNotIsInstance(btn, ttk.Button)

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_default_config_path_uses_appdata(self):
        import config_gui

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"APPDATA": tmp}, clear=False):
                path = config_gui.get_default_config_path()
                self.assertEqual(path, os.path.join(tmp, "BlackboardSentinel", ".env"))
                self.assertTrue(os.path.isdir(os.path.dirname(path)))

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_config_gui_mac_never_imported_on_win32(self):
        code = (
            "import sys; sys.path.insert(0, %r); "
            "import config_gui, tray_app, tray_icon, check_lms; "
            "assert 'config_gui_mac' not in sys.modules, 'config_gui_mac was imported on win32!'; "
            "assert 'AppKit' not in sys.modules, 'AppKit was imported on win32!'"
        ) % str(REPO_ROOT)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_windows_spec_excludes_config_gui_mac(self):
        spec_src = (REPO_ROOT / "BlackboardSentinel.spec").read_text(encoding="utf-8")
        self.assertIn("config_gui_mac", spec_src)


class TestWindowsIconAndNetwork(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_is_system_taskbar_light_reads_winreg(self):
        import winreg
        import tray_icon

        with mock.patch.object(winreg, "OpenKey", return_value="k") as mock_open, \
             mock.patch.object(winreg, "QueryValueEx", return_value=(1, winreg.REG_DWORD)), \
             mock.patch.object(winreg, "CloseKey") as mock_close:
            self.assertTrue(tray_icon.is_system_taskbar_light())
            mock_open.assert_called_once()
            mock_close.assert_called_once_with("k")

        with mock.patch.object(winreg, "OpenKey", return_value="k"), \
             mock.patch.object(winreg, "QueryValueEx", return_value=(0, winreg.REG_DWORD)), \
             mock.patch.object(winreg, "CloseKey"):
            self.assertFalse(tray_icon.is_system_taskbar_light())

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_windows_toast_and_wsl_use_create_no_window(self):
        import check_lms

        with mock.patch("subprocess.run") as mock_run:
            check_lms.send_windows_toast("Title", "Body")
            self.assertEqual(mock_run.call_args.kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
            self.assertEqual(mock_run.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("subprocess.run", side_effect=[FileNotFoundError(), mock.MagicMock(returncode=0)]) as mock_run:
            os.environ.pop("HERMES_JOB_ID", None)
            check_lms.send_to_chat("Hello")
            self.assertEqual(mock_run.call_args_list[-1].kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
            self.assertEqual(mock_run.call_args_list[-1].kwargs.get("stdin"), subprocess.DEVNULL)

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_installer_and_uninstaller_subprocess_use_no_window_and_devnull(self):
        import installer
        import uninstaller

        with mock.patch("subprocess.run") as mock_run:
            installer.stop_active_processes()
            self.assertEqual(mock_run.call_args.kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
            self.assertEqual(mock_run.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

        with mock.patch("subprocess.run") as mock_run:
            uninstaller.stop_active_processes()
            self.assertEqual(mock_run.call_args.kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
            self.assertEqual(mock_run.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

        with mock.patch("subprocess.run") as mock_run:
            uninstaller.remove_scheduled_task()
            self.assertEqual(mock_run.call_args.kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)
            self.assertEqual(mock_run.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_write_web_shortcut_uses_single_crlf_on_win32(self):
        import check_lms

        with tempfile.TemporaryDirectory() as tmp:
            sc = check_lms._write_web_shortcut(tmp, "Portal", "https://lms.university.edu/test")
            self.assertTrue(sc.endswith(".url"))
            raw = pathlib.Path(sc).read_bytes()
            self.assertNotIn(b"\r\r\n", raw)
            self.assertEqual(raw, b"[InternetShortcut]\r\nURL=https://lms.university.edu/test\r\n")

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_ssl_context_loads_system_cas_on_win32(self):
        import ssl
        import check_lms

        ctx = check_lms._get_ssl_context()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertGreater(len(ctx.get_ca_certs()), 0)

    def test_redirect_null_stdio_writes_to_app_log(self):
        import tray_app

        with tempfile.TemporaryDirectory() as tmp:
            orig_out, orig_err = sys.stdout, sys.stderr
            orig_handle = tray_app._NULL_STDIO_LOG_HANDLE
            try:
                sys.stdout = None
                sys.stderr = None
                log_path = tray_app._redirect_null_stdio(log_dir=tmp)
                self.assertTrue(log_path and log_path.endswith("app.log"))
                print("stdout-check")
                sys.stderr.write("stderr-check\n")
                sys.stderr.flush()
                if tray_app._NULL_STDIO_LOG_HANDLE is not None:
                    tray_app._NULL_STDIO_LOG_HANDLE.close()
            finally:
                sys.stdout = orig_out
                sys.stderr = orig_err
                tray_app._NULL_STDIO_LOG_HANDLE = orig_handle

            text = pathlib.Path(log_path).read_text(encoding="utf-8")
            self.assertIn("stdout-check", text)
            self.assertIn("stderr-check", text)

    def test_updater_version_comparison_and_cross_host_auth_strip(self):
        import urllib.request
        import updater

        self.assertTrue(updater.is_newer_version("v1.2.0", "1.1.11"))
        self.assertTrue(updater.is_newer_version("v1.1.12", "1.1.11"))
        self.assertFalse(updater.is_newer_version("v1.1.11", "1.1.11"))
        self.assertFalse(updater.is_newer_version("v1.1.10", "1.1.11"))

        handler = updater._CrossHostAuthStripRedirectHandler()
        orig_req = urllib.request.Request(
            "https://api.github.com/repos/org/app/releases/assets/123",
            headers={"Authorization": "Bearer secret-token", "Accept": "application/octet-stream"},
        )
        cross_req = handler.redirect_request(
            orig_req, None, 302, "Found", {}, "https://objects.githubusercontent.com/asset.exe"
        )
        self.assertIsNotNone(cross_req)
        self.assertNotIn("Authorization", cross_req.headers)
        self.assertNotIn("Authorization", cross_req.unredirected_hdrs)

        same_req = handler.redirect_request(
            orig_req, None, 302, "Found", {}, "https://api.github.com/repos/org/app/releases/assets/456"
        )
        self.assertIsNotNone(same_req)
        self.assertEqual(same_req.headers.get("Authorization"), "Bearer secret-token")

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific test")
    def test_updater_launch_silent_installer_detached_flags(self):
        import updater

        called = []
        with mock.patch("subprocess.Popen") as mock_popen, mock.patch("os._exit") as mock_exit:
            updater.launch_silent_installer(
                r"C:\Temp\BlackboardSentinelSetup.exe",
                before_exit_callback=lambda: called.append("cleaned"),
                exit_process=True,
            )
            args = mock_popen.call_args.args[0]
            self.assertEqual(
                args,
                [
                    r"C:\Temp\BlackboardSentinelSetup.exe",
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/FORCECLOSEAPPLICATIONS",
                    "/NORESTART",
                ],
            )
            expected_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            self.assertEqual(mock_popen.call_args.kwargs.get("creationflags"), expected_flags)
            self.assertEqual(called, ["cleaned"])
            mock_exit.assert_called_once_with(0)

    def test_onedir_spec_and_inno_setup_script_invariants(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        spec_text = (root / "BlackboardSentinel.spec").read_text(encoding="utf-8")
        self.assertIn("exclude_binaries=True", spec_text)
        self.assertIn("COLLECT(", spec_text)
        self.assertIn("'config_gui_mac'", spec_text)

        iss_text = (root / "installer.iss").read_text(encoding="utf-8")
        non_comment_iss = "\n".join(
            line for line in iss_text.splitlines() if not line.lstrip().startswith(";")
        )
        self.assertIn("PrivilegesRequired=lowest", non_comment_iss)
        self.assertIn("PrepareToInstall", non_comment_iss)
        self.assertIn("taskkill.exe", non_comment_iss)
        self.assertNotIn("skipifsilent", non_comment_iss.lower())


if __name__ == "__main__":
    unittest.main()
