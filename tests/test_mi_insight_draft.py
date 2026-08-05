"""월간 인사이트 초안: 재료 수집 + Actify mock 생성 + API 테스트."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api_server import app
from backend.app.services import mi_insight_draft as svc

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


@pytest.fixture(autouse=True)
def _isolate_draft_store(tmp_path, monkeypatch):
    """초안 저장소를 테스트마다 격리 (기본 경로 오염 방지)."""
    monkeypatch.setenv("INSIGHT_DRAFT_STORE_DIR", str(tmp_path / "drafts"))


def _run_canonical(events):
    return {"stage": "REVIEWED", "canonical_payload": {"events": events}}


def _event(event_id, valid_from, valid_to=None, **extra):
    event = {
        "event_id": event_id,
        "headline": f"헤드라인 {event_id}",
        "summary": "요약",
        "severity": "HIGH",
        "direction": "RISK_INCREASE",
        "impact_path": "DIRECT",
        "event_type": "GEOPOLITICAL",
        "affected_corridors": ["ASIA_EUROPE"],
        "valid_from": valid_from,
        "valid_to": valid_to,
        "internal_field": "응답에 포함되면 안 됨",
    }
    event.update(extra)
    return event


@pytest.fixture()
def run_store(tmp_path, monkeypatch):
    store = tmp_path / "mi_runs"
    store.mkdir()
    (store / "MI-RUN-1.json").write_text(
        json.dumps(_run_canonical([_event("MI-1", "2026-07-05")]), ensure_ascii=False),
        encoding="utf-8",
    )
    (store / "MI-RUN-2.json").write_text(
        json.dumps(
            {"stage": "REFINED", "response": {"events": [_event("MI-2", "2026-06-01", "2026-06-20")]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (store / "MI-RUN-3.json").write_text(
        json.dumps(_run_canonical([_event("MI-3", "2026-06-25", "2026-07-10")]), ensure_ascii=False),
        encoding="utf-8",
    )
    (store / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("MI_RUN_STORE_DIR", str(store))
    return store


def test_collect_mi_events_month_filter(run_store):
    events = svc.collect_mi_events("2026-07")
    ids = {e["event_id"] for e in events}
    # 7월 건 + 6월 시작·7월 종료 건 포함, 6월 종결 건 제외
    assert ids == {"MI-1", "MI-3"}
    # 요약 필드만 추출 (낸부 필드 제외)
    assert "internal_field" not in events[0]
    assert events[0]["severity"] == "HIGH"


def test_collect_mi_events_empty_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_RUN_STORE_DIR", str(tmp_path / "empty"))
    assert svc.collect_mi_events("2026-07") == []


def _set_actify_env(monkeypatch):
    monkeypatch.setenv("ACTIFY_BASE_URL", "http://fake")
    monkeypatch.setenv("ACTIFY_API_KEY", "fake")
    monkeypatch.setenv("ACTIFY_USER", "tester")


VALID_ANSWER = json.dumps(
    {
        "key_changes": ["핵심변화1", "핵심변화2"],
        "sections": [
            {"key": "sea_europe", "title": "유럽 권역 동향", "body": "본문"},
            {"key": "key_events", "title": "주요 이벤트", "body": "본문2"},
        ],
        "monitoring_points": ["홍해 동향"],
        "disclaimer": "검토용 초안입니다.",
    }
)

# key_changes 없는 구형 응답도 하위호환으로 받아들인다 (기본값 빈 리스트)
LEGACY_ANSWER = json.dumps(
    {
        "sections": [{"key": "k", "title": "t", "body": "b"}],
        "monitoring_points": [],
        "disclaimer": "d",
    }
)


def test_generate_draft_success(run_store, monkeypatch):
    _set_actify_env(monkeypatch)
    monkeypatch.setattr(
        svc, "collect_leadtime_highlights", lambda month: {"top_changes": [{"route": "아드리아", "delta": 3.0}]}
    )
    monkeypatch.setattr(svc, "collect_schedule_summary", lambda: {"active_transports": 5})
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": VALID_ANSWER, "conversation_id": ""}
        )(),
    )
    # 지도 라벨 생성 훅 — 실제 Actify 호출 방지
    monkeypatch.setattr(
        "backend.app.services.mi_map_labels.generate_map_labels",
        lambda events: {},
    )
    result = svc.generate_insight_draft(month="2026-07", include_leadtime=True)
    assert result["month"] == "2026-07"
    assert len(result["draft"]["sections"]) == 2
    assert result["draft"]["key_changes"] == ["핵심변화1", "핵심변화2"]
    assert result["draft"]["monitoring_points"] == ["홍해 동향"]
    summary = result["materials_summary"]
    assert summary == {"events_used": 2, "leadtime_used": True, "summary_used": True}


def test_generate_draft_triggers_map_label_refresh(run_store, monkeypatch):
    """초안 생성 성공 시 지도 라벨 갱신 훅이 레지스트리 이벤트로 호출된다."""
    _set_actify_env(monkeypatch)
    monkeypatch.setattr(svc, "collect_leadtime_highlights", lambda month: None)
    monkeypatch.setattr(svc, "collect_schedule_summary", lambda: None)
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": VALID_ANSWER, "conversation_id": ""}
        )(),
    )
    monkeypatch.setattr(
        "backend.app.services.mi_event_registry.list_events",
        lambda **kw: {"events": [{"event_id": "EV-9", "status": "ACTIVE"}]},
    )
    calls: list[list] = []
    monkeypatch.setattr(
        "backend.app.services.mi_map_labels.generate_map_labels",
        lambda events: calls.append(events) or {},
    )
    svc.generate_insight_draft(month="2026-07")
    assert calls == [[{"event_id": "EV-9", "status": "ACTIVE"}]]


def test_generate_draft_legacy_response_without_key_changes(run_store, monkeypatch):
    """key_changes가 없는 구형 Actify 응답도 빈 리스트로 하위호환 처리."""
    _set_actify_env(monkeypatch)
    monkeypatch.setattr(svc, "collect_leadtime_highlights", lambda month: None)
    monkeypatch.setattr(svc, "collect_schedule_summary", lambda: None)
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": LEGACY_ANSWER, "conversation_id": ""}
        )(),
    )
    monkeypatch.setattr(
        "backend.app.services.mi_map_labels.generate_map_labels",
        lambda events: {},
    )
    result = svc.generate_insight_draft(month="2026-07", include_leadtime=False)
    assert result["draft"]["key_changes"] == []


def test_generate_draft_not_configured(monkeypatch):
    for key in ("ACTIFY_BASE_URL", "ACTIFY_API_KEY", "ACTIFY_USER"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(svc.ActifyNotConfiguredError):
        svc.generate_insight_draft(month="2026-07")


def test_generate_draft_broken_response(run_store, monkeypatch):
    _set_actify_env(monkeypatch)
    monkeypatch.setattr(svc, "collect_leadtime_highlights", lambda month: None)
    monkeypatch.setattr(svc, "collect_schedule_summary", lambda: None)
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": "JSON이 아님", "conversation_id": ""}
        )(),
    )
    with pytest.raises(RuntimeError):
        svc.generate_insight_draft(month="2026-07", include_leadtime=False)


# ---------- API ----------

def test_api_insight_draft_ok(monkeypatch):
    monkeypatch.setattr(
        svc,
        "generate_insight_draft",
        lambda month=None, include_leadtime=True, regenerate=False: {
            "draft": {"sections": [], "monitoring_points": [], "disclaimer": ""},
            "materials_summary": {"events_used": 0, "leadtime_used": False, "summary_used": False},
            "month": month or "2026-07",
            "generated_at": "2026-07-19T00:00:00",
            "regenerated": True,
        },
    )
    client = TestClient(app)
    resp = client.post("/api/report/insight-draft", json={"month": "2026-07"})
    assert resp.status_code == 200
    assert resp.json()["month"] == "2026-07"


def test_api_insight_draft_503(monkeypatch):
    def _raise(**kwargs):
        raise svc.ActifyNotConfiguredError("Actify 미설정")

    monkeypatch.setattr(svc, "generate_insight_draft", _raise)
    client = TestClient(app)
    resp = client.post("/api/report/insight-draft", json={})
    assert resp.status_code == 503


def test_api_insight_draft_bad_month_422():
    client = TestClient(app)
    resp = client.post("/api/report/insight-draft", json={"month": "2026-13"})
    assert resp.status_code == 422
    assert client.post("/api/report/insight-draft", json={"month": "July"}).status_code == 422
