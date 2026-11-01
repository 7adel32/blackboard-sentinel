# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('dist/BlackboardSentinel.exe', '.'),
    ('dist/uninstall.exe', '.'),
    ('assets', 'assets')
]

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['winreg', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'win32com', 'win32com.client'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BlackboardSentinelSetup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon_app.ico'],
)
