# -*- mode: python ; coding: utf-8 -*-
# Blackboard Sentinel - macOS PyInstaller Spec File
# Builds an agent/menu bar .app bundle with LSUIElement enabled (no Dock icon).

import sys
import os

block_cipher = None

a = Analysis(
    ['tray_app.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[
        'lms_deadlines',
        'lms_grades',
        'config_gui',
        'tray_icon',
        'check_lms',
        'pystray',
        'docx',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
        'objc',
        'AppKit',
        'Foundation',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BlackboardSentinel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BlackboardSentinel',
)

app = BUNDLE(
    coll,
    name='BlackboardSentinel.app',
    icon='assets/icon_app.icns',
    bundle_identifier='com.sentinel.blackboard',
    info_plist={
        'CFBundleName': 'Blackboard Sentinel',
        'CFBundleDisplayName': 'Blackboard Sentinel',
        'CFBundleIdentifier': 'com.sentinel.blackboard',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Hides Dock icon; runs strictly as a Menu Bar accessory
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
    },
)
