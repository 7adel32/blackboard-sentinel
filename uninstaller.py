#!/usr/bin/env python3
"""
Blackboard Sentinel - Standalone Windows Uninstaller
Stops running processes, removes Windows startup & Start Menu shortcuts,
cleans up configuration & cache, deletes registry uninstall entries,
and completely removes the application installation directory.
"""

import os
import sys
import time
import winreg
import subprocess
import tkinter as tk
from tkinter import messagebox

def stop_active_processes():
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", 
             "Get-Process -Name 'BlackboardSentinel' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; "
             "Get-Process -Name 'pythonw' -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'tray_app.py' } | Stop-Process -Force -ErrorAction SilentlyContinue"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception:
        pass


def remove_shortcuts():
    appdata = os.getenv("APPDATA", "")
    if appdata:
        # 1. Startup shortcut
        startup_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "BlackboardSentinel.lnk")
        if os.path.exists(startup_lnk):
            try:
                os.remove(startup_lnk)
            except Exception:
                pass

        # 2. Start menu shortcuts
        menu_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Blackboard Sentinel.lnk")
        if os.path.exists(menu_lnk):
            try:
                os.remove(menu_lnk)
            except Exception:
                pass

        uninst_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Uninstall Blackboard Sentinel.lnk")
        if os.path.exists(uninst_lnk):
            try:
                os.remove(uninst_lnk)
            except Exception:
                pass


def remove_scheduled_task():
    try:
        subprocess.run(
            ["schtasks", "/delete", "/tn", "BlackboardSentinel", "/f"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception:
        pass


def remove_registry_entry():
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackboardSentinel"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def wipe_appdata_and_state():
    import shutil
    appdata = os.getenv("APPDATA", "")
    local_appdata = os.getenv("LOCALAPPDATA", "")

    if appdata:
        cfg_dir = os.path.join(appdata, "BlackboardSentinel")
        if os.path.exists(cfg_dir):
            try:
                shutil.rmtree(cfg_dir, ignore_errors=True)
            except Exception:
                pass

    if local_appdata:
        local_dir = os.path.join(local_appdata, "BlackboardSentinel")
        if os.path.exists(local_dir):
            try:
                shutil.rmtree(local_dir, ignore_errors=True)
            except Exception:
                pass

    hermes_state = os.path.expanduser("~/.hermes/state/lms_tracker_state.json")
    if os.path.exists(hermes_state):
        try:
            os.remove(hermes_state)
        except Exception:
            pass


def get_install_dir():
    # If compiled with PyInstaller, sys.executable is the uninstaller binary
    own_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    return own_dir


def self_delete_and_exit(install_dir):
    # Schedule directory removal after uninstaller process exits
    if os.path.exists(install_dir):
        clean_dir = install_dir.rstrip("\\/")
        # Ensure we only delete our own BlackboardSentinel folder
        if "BlackboardSentinel" in os.path.basename(clean_dir):
            cmd = f'timeout /t 2 /nobreak >nul & rmdir /s /q "{clean_dir}"'
            subprocess.Popen(
                ["cmd.exe", "/c", cmd],
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
    sys.exit(0)


def perform_uninstall(quiet=False):
    stop_active_processes()
    remove_shortcuts()
    remove_scheduled_task()
    remove_registry_entry()
    wipe_appdata_and_state()

    install_dir = get_install_dir()

    if not quiet:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "Blackboard Sentinel Uninstalled",
                "Blackboard Sentinel was successfully removed from your computer."
            )
            root.destroy()
        except Exception:
            pass

    self_delete_and_exit(install_dir)


def main():
    quiet = "--quiet" in sys.argv or "-q" in sys.argv or "--silent" in sys.argv

    if not quiet:
        root = tk.Tk()
        root.withdraw()
        # Bring dialog to front
        root.attributes("-topmost", True)
        confirm = messagebox.askyesno(
            "Uninstall Blackboard Sentinel",
            "Are you sure you want to completely remove Blackboard Sentinel and all of its components?",
            parent=root
        )
        root.destroy()
        if not confirm:
            sys.exit(0)

    perform_uninstall(quiet=quiet)


if __name__ == "__main__":
    main()
