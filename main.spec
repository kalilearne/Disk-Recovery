# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py','data_wipe.py','disk_reader.py','disk_recovery_tool.py','disk_utils.py','fat32_recovery.py','file_recovery.py','file_signature_recovery.py',
    'file_system_reader.py','ntfs_recovery.py','disk_image_snapshot.py','ui_components.py','virtual_disk.py','disk_utils_fallback.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='DISK-recv_0.93',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='favicon.ico',
)
