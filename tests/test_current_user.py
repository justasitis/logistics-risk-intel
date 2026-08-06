"""현재 사용자 정보 API 테스트 — 외부 MI 정제 탭 관리 권한."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from api_server import app

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


def _set_user(monkeypatch, username: str):
    monkeypatch.setattr(
        "backend.app.core.user_path.current_username", lambda: username,
    )


def test_me_grants_manage_mi_to_publish_user(monkeypatch):
    """REPORT_PUBLISH_USERS 사용자는 can_manage_mi=True (대소문자 무관)."""
    _set_user(monkeypatch, "SO23132")
    body = TestClient(app).get("/api/me").json()
    assert body["username"] == "so23132"
    assert body["can_manage_mi"] is True


def test_me_denies_manage_mi_to_other_user(monkeypatch):
    _set_user(monkeypatch, "viewer01")
    body = TestClient(app).get("/api/me").json()
    assert body["username"] == "viewer01"
    assert body["can_manage_mi"] is False
