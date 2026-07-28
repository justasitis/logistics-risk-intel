# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙 — LogisticsRiskTray (트레이 알림박스, 콘솔 없음).

빌드 (프로젝트 루트에서):
  pyinstaller build/logistics_risk_tray.spec --noconfirm --workpath build/work-tray --distpath build/dist-tray
"""

hiddenimports = [
    "win32timezone",
]

a = Analysis(
    ["../tray/tray_app.py"],
    pathex=["../tray"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LogisticsRiskTray",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 트레이 앱 — 콘솔 창 없음
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LogisticsRiskTray",
)
