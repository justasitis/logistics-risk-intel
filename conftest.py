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


@pytest.fixture(autouse=True)
def _isolate_sharepoint_root(tmp_path, monkeypatch):
    """SharePoint 루트를 격리 — 테스트가 실제 동기화 폴터를 건드리지 않도록.

    기본 루트(C:\\Users\\<user>\\SK on\\M365_TtNUJmLE - 데이터_접근금지)가
    개발 PC에 실재하므로, 환경변수 미설정 테스트가 실제 폴터에 쓰는 사고를 막는다.
    개별 테스트가 MARINESIA_SHAREPOINT_ROOT를 직접 설정하면 그 값이 우선한다
    (이 fixture는 설정돼 있지 않을 때만 기본값을 덮어쓴다).
    """
    import os

    from backend.app.core import marinesia_settings

    if not os.environ.get("MARINESIA_SHAREPOINT_ROOT"):
        monkeypatch.setenv(
            "MARINESIA_SHAREPOINT_ROOT", str(tmp_path / "sp_root"),
        )
    marinesia_settings.get_marinesia_settings.cache_clear()
    yield
    marinesia_settings.get_marinesia_settings.cache_clear()


@pytest.fixture
def data_dir(tmp_path):
    """테스트용 임시 데이터 디렉터리."""
    directory = tmp_path / "data"
    directory.mkdir()
    return directory
