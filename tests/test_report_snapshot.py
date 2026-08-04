"""MI 리포트 게시본(스냅샷) API 테스트 — 권한/저장/조회."""
from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from backend.app.core import marinesia_settings

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


FAKE_REPORT = {
    "generated_at": "2026-08-04T09:00:00",
    "source": "B-LAP bl_info",
    "definitions": {},
    "month_columns": [],
    "groups": [],
}


@pytest.fixture
def sharepoint_root(tmp_path, monkeypatch):
    """SharePoint 루트 격리 + 리드타임/override는 fake로."""
    root = tmp_path / "LogisticsRisk"
    monkeypatch.setenv("MARINESIA_SHAREPOINT_ROOT", str(root))
    monkeypatch.setenv("INSIGHT_DRAFT_STORE_DIR", str(tmp_path / "drafts"))
    marinesia_settings.get_marinesia_settings.cache_clear()
    monkeypatch.setattr(
        "services.leadtime_report_service.fetch_bl_info",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "services.leadtime_report_service.compute_leadtime_report",
        lambda *a, **kw: dict(FAKE_REPORT),
    )
    monkeypatch.setattr(
        api_server, "_apply_leadtime_overrides", lambda payload: payload,
    )
    yield root
    marinesia_settings.get_marinesia_settings.cache_clear()


def _set_user(monkeypatch, username: str):
    monkeypatch.setattr(
        "backend.app.core.user_path.current_username", lambda: username,
    )


def test_publish_forbidden_for_other_user(sharepoint_root, monkeypatch):
    _set_user(monkeypatch, "someone_else")
    resp = TestClient(app).post("/api/report/snapshot/publish")
    assert resp.status_code == 403
    assert not (sharepoint_root / "MI" / "report_snapshot.json").exists()


def test_publish_and_read_snapshot(sharepoint_root, monkeypatch):
    _set_user(monkeypatch, "so23132")
    client = TestClient(app)

    # 게시 전: 게시본 없음 + 권한 있음
    before = client.get("/api/report/snapshot").json()
    assert before["exists"] is False
    assert before["can_publish"] is True

    published = client.post("/api/report/snapshot/publish")
    assert published.status_code == 200
    body = published.json()
    assert body["published_by"] == "so23132"
    assert body["report"]["source"] == "B-LAP bl_info"
    assert body["insight"] is None  # 초안 저장소 비어 있음

    # 파일이 SharePoint 경로에 atomic으로 저장됨
    saved = sharepoint_root / "MI" / "report_snapshot.json"
    assert saved.exists()
    on_disk = json.loads(saved.read_text(encoding="utf-8"))
    assert on_disk["published_by"] == "so23132"

    # 다른 사용자는 읽기만 가능
    _set_user(monkeypatch, "viewer01")
    after = client.get("/api/report/snapshot").json()
    assert after["exists"] is True
    assert after["can_publish"] is False
    assert after["snapshot"]["published_by"] == "so23132"
    assert TestClient(app).post("/api/report/snapshot/publish").status_code == 403


def test_publish_includes_saved_insight(sharepoint_root, monkeypatch):
    """저장된 인사이트 초안이 있으면 게시본에 포함."""
    import os
    from datetime import date

    from backend.app.services.insight_draft_store import InsightDraftStore

    month = date.today().isoformat()[:7]
    InsightDraftStore().save(
        month,
        {
            "draft": {
                "key_changes": ["변화1"],
                "sections": [],
                "monitoring_points": [],
                "disclaimer": "검토용",
            },
            "materials_summary": {
                "events_used": 0,
                "leadtime_used": True,
                "summary_used": False,
            },
            "generated_at": "2026-08-04T09:00:00",
        },
    )
    _set_user(monkeypatch, "so23364")
    resp = TestClient(app).post("/api/report/snapshot/publish")
    assert resp.status_code == 200
    body = resp.json()
    assert body["published_by"] == "so23364"
    assert body["insight"]["draft"]["key_changes"] == ["변화1"]
    assert body["month"] == month
