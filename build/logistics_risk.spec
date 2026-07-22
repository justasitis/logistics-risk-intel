# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙 — LogisticsRisk onedir 패키지.

빌드 (프로젝트 루트에서):
  pyinstaller build/logistics_risk.spec --noconfirm --workpath build/work --distpath build/dist

데이터 수집:
  - frontend/dist: api_server.py가 _MEIPASS/frontend/dist 를 StaticFiles로 서빙
  - searoute: 항로 네트워크 데이터(geojson)
  - folium/branca: 지도 HTML 템플릿
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [("../frontend/dist", "frontend/dist")]
# 앱 데이터 파일 (frozen에서는 _MEIPASS 기준으로 읽음)
datas += [
    ("../data", "data"),
    ("../backend/data", "backend/data"),
    ("../backend/app/data", "backend/app/data"),
    ("../backend/app/prompts", "backend/app/prompts"),
]
datas += collect_data_files("searoute")
datas += collect_data_files("folium")
datas += collect_data_files("branca")

hiddenimports = [
    # uvicorn 낸부 (동적 import)
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # 런타임에 문자열로 참조되는 앱 엔트리
    "api_server",
]
hiddenimports += collect_submodules("backend.app")
hiddenimports += collect_submodules("services")

a = Analysis(
    ["launcher.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
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
    name="LogisticsRisk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LogisticsRisk",
)
