#!/usr/bin/env python3
"""
Blackboard Sentinel - Standalone Windows Installer
Gracefully stops active processes, installs the application and uninstaller to
%LOCALAPPDATA%\\Programs\\BlackboardSentinel, creates Start Menu and Startup shortcuts,
registers in Windows Add/Remove Programs, and launches the updated application.
"""

import os
import sys
import time
import winreg
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, messagebox


def stop_active_processes():
    """Ensure no running BlackboardSentinel instances block file copy."""
    try:
        my_pid = os.getpid()
        ps_cmd = (
            f"Get-Process -Name 'BlackboardSentinel' -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.Id -ne {my_pid} }} | Stop-Process -Force -ErrorAction SilentlyContinue; "
            f"Get-Process -Name 'pythonw' -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.CommandLine -match 'tray_app.py' }} | Stop-Process -Force -ErrorAction SilentlyContinue"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        time.sleep(0.8)
    except Exception:
        pass


def get_source_exe(filename):
    """Find the source executable in bundle, script dir, or dist."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(bundled):
            return bundled

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "dist", filename),
        os.path.join(base_dir, filename),
        os.path.join(os.path.expanduser("~"), "Downloads", filename)
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def create_shortcut(target, shortcut_path, description=""):
    """Create a Windows shortcut (.lnk)."""
    try:
        os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = os.path.dirname(target)
            shortcut.Description = description
            shortcut.save()
            return
        except Exception:
            pass

        # Fallback to PowerShell
        ps_code = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_path}'); "
            f"$s.TargetPath = '{target}'; "
            f"$s.WorkingDirectory = '{os.path.dirname(target)}'; "
            f"$s.Description = '{description}'; "
            f"$s.Save()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception:
        pass


def register_in_add_remove(install_dir, installed_exe, installed_uninst):
    """Register in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall."""
    reg_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackboardSentinel"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Blackboard Sentinel")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0.0")
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Developer")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, f"{installed_exe},0")
            if os.path.exists(installed_uninst):
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{installed_uninst}"')
                winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f'"{installed_uninst}" --quiet')
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass


def perform_install(status_callback=None):
    """Execute installation / update steps."""
    def update_status(text):
        if status_callback:
            status_callback(text)

    update_status("Stopping active processes...")
    stop_active_processes()

    install_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "BlackboardSentinel")
    os.makedirs(install_dir, exist_ok=True)

    # 1. Copy BlackboardSentinel.exe
    update_status("Copying application binaries...")
    src_main = get_source_exe("BlackboardSentinel.exe")
    installed_exe = os.path.join(install_dir, "BlackboardSentinel.exe")
    if src_main and os.path.abspath(src_main) != os.path.abspath(installed_exe):
        shutil.copy2(src_main, installed_exe)

    # 2. Copy uninstall.exe
    src_uninst = get_source_exe("uninstall.exe")
    installed_uninst = os.path.join(install_dir, "uninstall.exe")
    if src_uninst and os.path.abspath(src_uninst) != os.path.abspath(installed_uninst):
        shutil.copy2(src_uninst, installed_uninst)

    # 3. Create Shortcuts
    update_status("Creating shortcuts...")
    appdata = os.getenv("APPDATA", "")
    if appdata:
        startup_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "BlackboardSentinel.lnk")
        start_menu_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Blackboard Sentinel.lnk")
        uninstall_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Uninstall Blackboard Sentinel.lnk")

        create_shortcut(installed_exe, startup_lnk, "Blackboard Sentinel Course Monitor")
        create_shortcut(installed_exe, start_menu_lnk, "Blackboard Sentinel Course Monitor")
        if os.path.exists(installed_uninst):
            create_shortcut(installed_uninst, uninstall_lnk, "Uninstall Blackboard Sentinel")

    # 4. Register in Windows Add/Remove Programs
    update_status("Registering in Windows Settings...")
    register_in_add_remove(install_dir, installed_exe, installed_uninst)

    # 5. Launch updated application
    update_status("Launching application...")
    if os.path.exists(installed_exe):
        subprocess.Popen([installed_exe], cwd=install_dir, close_fds=True)

    update_status("Installation complete.")
    return True


def run_gui():
    root = tk.Tk()
    root.title("Blackboard Sentinel Installer")
    root.geometry("460x220")
    root.resizable(False, False)
    root.configure(bg="#0f172a")

    icon_path = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets", "icon_app.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    title_label = tk.Label(
        root,
        text="Blackboard Sentinel Installer",
        font=("Segoe UI", 14, "bold"),
        fg="#f8fafc",
        bg="#0f172a"
    )
    title_label.pack(pady=(20, 10))

    status_var = tk.StringVar(value="Ready to install or update.")
    status_label = tk.Label(
        root,
        textvariable=status_var,
        font=("Segoe UI", 10),
        fg="#94a3b8",
        bg="#0f172a"
    )
    status_label.pack(pady=(5, 15))

    progress = ttk.Progressbar(root, mode="indeterminate", length=360)
    progress.pack(pady=(0, 20))

    def on_install():
        btn_install.config(state="disabled")
        progress.start(10)

        def worker():
            try:
                perform_install(status_callback=lambda msg: root.after(0, status_var.set, msg))
                time.sleep(0.5)
                root.after(0, on_done)
            except Exception as e:
                err_msg = str(e)
                root.after(0, lambda: messagebox.showerror("Installation Error", f"Installation failed: {err_msg}"))
                root.after(0, lambda: btn_install.config(state="normal"))
                root.after(0, progress.stop)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def on_done():
        progress.stop()
        messagebox.showinfo("Installation Complete", "Blackboard Sentinel has been installed and launched successfully.")
        root.destroy()

    btn_frame = tk.Frame(root, bg="#0f172a")
    btn_frame.pack(fill="x", padx=30)

    btn_install = tk.Button(
        btn_frame,
        text="Install / Update",
        font=("Segoe UI", 10, "bold"),
        bg="#3b82f6",
        fg="white",
        activebackground="#2563eb",
        activeforeground="white",
        relief="flat",
        padx=16,
        pady=6,
        cursor="hand2",
        command=on_install
    )
    btn_install.pack(side="right", padx=5)

    btn_cancel = tk.Button(
        btn_frame,
        text="Cancel",
        font=("Segoe UI", 10),
        bg="#334155",
        fg="#cbd5e1",
        activebackground="#475569",
        activeforeground="#ffffff",
        relief="flat",
        padx=12,
        pady=6,
        cursor="hand2",
        command=root.destroy
    )
    btn_cancel.pack(side="right", padx=5)

    root.mainloop()


def main():
    if "--quiet" in sys.argv or "-q" in sys.argv or "/S" in sys.argv:
        perform_install()
    else:
        run_gui()


if __name__ == "__main__":
    main()
