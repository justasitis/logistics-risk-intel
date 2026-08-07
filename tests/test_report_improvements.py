"""리포트 개선 3건 테스트: draft 저장/복원/편집, leadtime override 병합."""
import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from backend.app.services import insight_draft_store as store_mod
from backend.app.services import mi_insight_draft as svc
from services import leadtime_report_service as leadtime_svc

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


@pytest.fixture()
def draft_store(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_DRAFT_STORE_DIR", str(tmp_path / "drafts"))
    monkeypatch.setenv("MI_RUN_STORE_DIR", str(tmp_path / "runs"))
    return tmp_path / "drafts"


SAMPLE_DRAFT = {
    "sections": [{"key": "key_events", "title": "주요 이벤트", "body": "본문"}],
    "monitoring_points": ["홍해"],
    "disclaimer": "검토용",
}


# ---------- ② 초안 저장/복원/편집 ----------

def test_store_roundtrip(draft_store):
    store = store_mod.InsightDraftStore()
    record = store.save("2026-07", {"draft": SAMPLE_DRAFT, "generated_at": "t0"})
    assert record["draft_id"] == "INS-202607"
    assert record["month"] == "2026-07"
    loaded = store.load("2026-07")
    assert loaded["draft"] == SAMPLE_DRAFT
    with pytest.raises(store_mod.InsightDraftNotFoundError):
        store.load("2026-08")


def test_generate_returns_existing_when_not_regenerate(draft_store, monkeypatch):
    # Actify 미설정 상태에서도 기존 초안이 있으면 반환해야 함
    for key in ("ACTIFY_BASE_URL", "ACTIFY_API_KEY", "ACTIFY_USER"):
        monkeypatch.delenv(key, raising=False)
    store_mod.InsightDraftStore().save(
        "2026-07", {"draft": SAMPLE_DRAFT, "generated_at": "t0"}
    )
    result = svc.generate_insight_draft(month="2026-07", regenerate=False)
    assert result["regenerated"] is False
    assert result["draft"] == SAMPLE_DRAFT


def test_generate_regenerate_overwrites(draft_store, monkeypatch):
    monkeypatch.setenv("ACTIFY_BASE_URL", "http://fake")
    monkeypatch.setenv("ACTIFY_API_KEY", "fake")
    monkeypatch.setenv("ACTIFY_USER", "tester")
    store_mod.InsightDraftStore().save(
        "2026-07", {"draft": SAMPLE_DRAFT, "generated_at": "t0"}
    )
    answer = json.dumps(
        {"sections": [], "monitoring_points": [], "disclaimer": "new"}
    )
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": answer, "conversation_id": ""}
        )(),
    )
    monkeypatch.setattr(svc, "collect_leadtime_highlights", lambda month: None)
    monkeypatch.setattr(svc, "collect_schedule_summary", lambda: None)
    result = svc.generate_insight_draft(month="2026-07", regenerate=True)
    assert result["regenerated"] is True
    assert result["draft"]["disclaimer"] == "new"
    # 저장소에도 덮어쓰기 반영
    assert store_mod.InsightDraftStore().load("2026-07")["draft"]["disclaimer"] == "new"


def test_api_draft_get_put(draft_store):
    store_mod.InsightDraftStore().save(
        "2026-07",
        {"draft": SAMPLE_DRAFT, "materials_summary": {}, "generated_at": "t0"},
    )
    client = TestClient(app)
    resp = client.get("/api/report/insight-draft/2026-07")
    assert resp.status_code == 200
    assert resp.json()["draft_id"] == "INS-202607"

    edited = {**SAMPLE_DRAFT, "sections": [{"key": "key_events", "title": "주요 이벤트", "body": "수정된 본문"}]}
    resp = client.put("/api/report/insight-draft/2026-07", json={"draft": edited})
    assert resp.status_code == 200
    assert resp.json()["revised_at"]
    loaded = client.get("/api/report/insight-draft/2026-07").json()
    assert loaded["draft"]["sections"][0]["body"] == "수정된 본문"

    # 404 / 422
    assert client.get("/api/report/insight-draft/2026-08").status_code == 404
    assert client.get("/api/report/insight-draft/2026-13").status_code == 422
    assert (
        client.put("/api/report/insight-draft/2026-07", json={"draft": {"bad": 1}}).status_code
        == 422
    )


# ---------- ③ leadtime override ----------

@pytest.fixture()
def override_env(tmp_path, monkeypatch):
    path = tmp_path / "leadtime_overrides.json"
    monkeypatch.setattr(api_server, "LEADTIME_OVERRIDES_PATH", path)
    monkeypatch.setattr(
        leadtime_svc,
        "fetch_bl_info",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "dprt": "KRPUS", "arvl": "SIKOP", "stopby": "SUEZ", "stopby_nm": "",
                    "cargo_type3": "FCL", "trpr_mode": "100", "onboard_date": "2026-05-10",
                    "atd": None, "ata": "2026-06-09",
                    "eta": None, "eta_date": None, "etd": None,
                }
            ]
        ),
    )
    api_server._CACHE.clear()
    yield path
    api_server._CACHE.clear()


def test_leadtime_override_merge_and_reset(override_env):
    client = TestClient(app)
    key = "ADRIA_SUEZ|KR|Avg|2026-05"

    resp = client.put(
        "/api/report/leadtime/overrides", json={"overrides": {key: 45.0}}
    )
    assert resp.status_code == 200

    body = client.get("/api/report/leadtime?months=12").json()
    group = next(g for g in body["groups"] if g["group_id"] == "ADRIA_SUEZ")
    row = next(r for r in group["rows"] if r["country"] == "KR" and r["stat"] == "Avg")
    assert row["cells"]["2026-05"] == 45.0
    assert key in body["edited_cells"]

    # 캐시 무효화 확인: override 변경 즉시 반영
    client.put("/api/report/leadtime/overrides", json={"overrides": {key: 50.0}})
    body = client.get("/api/report/leadtime?months=12").json()
    group = next(g for g in body["groups"] if g["group_id"] == "ADRIA_SUEZ")
    row = next(r for r in group["rows"] if r["country"] == "KR" and r["stat"] == "Avg")
    assert row["cells"]["2026-05"] == 50.0

    # 초기화
    client.delete("/api/report/leadtime/overrides")
    body = client.get("/api/report/leadtime?months=12").json()
    group = next(g for g in body["groups"] if g["group_id"] == "ADRIA_SUEZ")
    row = next(r for r in group["rows"] if r["country"] == "KR" and r["stat"] == "Avg")
    assert row["cells"]["2026-05"] == 30.0
    assert body["edited_cells"] == []
