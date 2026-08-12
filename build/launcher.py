"""LogisticsRisk exe 진입점.

frozen(PyInstaller) 여부에 따라 base dir를 결정하고, base dir의 .env를 먼저
로드한 뒤 uvicorn으로 api_server를 기동한다. api_server 자첼 로더는
Path(__file__) 기준이라 frozen에서는 _MEIPASS를 가리키므로, exe 옆의 .env는
이 런처가 먼저 읽어야 한다(load_dotenv는 기존 환경변수를 덮어쓰지 않는다).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_URL = "http://127.0.0.1:8000"


def _open_app_mode(url: str) -> None:
    """Edge 앱 모드(--app=)로 연다. 실패 시 기본 브라우저 폴."""
    edge = shutil.which("msedge") or shutil.which("msedge.exe")
    try:
        if edge:
            subprocess.Popen([edge, f"--app={url}"])
            return
        # PATH에 없으면 Windows start 명령의 Edge 별칭으로 시도
        subprocess.Popen(["cmd", "/c", "start", "msedge", f"--app={url}"])
    except OSError:
        webbrowser.open(url)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


BASE_DIR = _base_dir()

# api_server 및 services/backend 패키지 import 경로 + 상대경로 기준 통일
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # dotenv 미설치 환경에서는 OS 환경변수만 사용
    pass


def _open_browser() -> None:
    time.sleep(3)
    _open_app_mode(APP_URL)


def main() -> None:
    print("=" * 60)
    print(" Logistics Risk Intelligence (VDI exe)")
    print(f" 주소: {APP_URL}")
    print(" 종료하려면 이 창을 닫으세요.")
    print("=" * 60)
    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn

    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
