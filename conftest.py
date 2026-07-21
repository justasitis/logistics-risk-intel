"""pytest 공통 설정.

- 프로젝트 루트를 sys.path에 추가 (services.*, backend.* import용)
- 외부 네트워크 호출(requests/httpx)을 autouse로 차단
- tmp 데이터 디렉터리 fixture 제공
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _block_external_http(request, monkeypatch):
    """외부 시스템(Denodo, SharePoint REST, Actify) HTTP 호출을 막는다.

    순수 로직 테스트에서 실수로 네트워크를 타는 경우를 즉시 실패시킨다.
    requests/httpx가 설치돼 있지 않은 최소 환경에서는 조용히 건너뛴다.
    """

    def _raise(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError(
            "테스트에서 외부 HTTP 호출이 감지됐습니다. "
            "외부 호출은 monkeypatch로 대체하세요."
        )

    try:
        import requests

        monkeypatch.setattr(
            requests.sessions.Session, "request", _raise
        )
    except ImportError:
        pass

    try:
        import httpx

        monkeypatch.setattr(httpx.Client, "request", _raise)
        monkeypatch.setattr(httpx.AsyncClient, "request", _raise)
    except ImportError:
        pass


@pytest.fixture
def data_dir(tmp_path):
    """테스트용 임시 데이터 디렉터리."""
    directory = tmp_path / "data"
    directory.mkdir()
    return directory
