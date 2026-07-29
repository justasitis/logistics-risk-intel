"""레지스트리 map-zones / 종합 정제(review) / 제안 반영(apply) 테스트."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api_server import app
from backend.app.services import mi_event_registry as reg
from backend.app.services import mi_registry_review as rev

_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


def _registry_payload():
    return {
        "version": 1,
        "reference_date": "2026-07-19",
        "events": [
            {
                "event_id": "MIREG-AAAA1111",
                "status": "ACTIVE",
                "first_seen": "2026-07-13",
                "last_seen": "2026-07-19",
                "sighting_count": 4,
                "sighting_dates": ["2026-07-13", "2026-07-19"],
                "headline": "홍해 선박 공격",
                "summary": "요약",
                "severity": "HIGH",
                "locations": ["Red Sea"],
                "corridors": ["ASIA_EUROPE"],
                "keywords": ["attack"],
                "source_candidate_ids": ["C1"],
                "evidence": [{"article_id": "A1", "url": "https://x/1"}],
                "reactivated": False,
            },
            {
                "event_id": "MIREG-BBBB2222",
                "status": "IMPROVING",
                "first_seen": "2026-07-01",
                "last_seen": "2026-07-10",
                "sighting_count": 2,
                "sighting_dates": ["2026-07-01", "2026-07-10"],
                "headline": "홍해 공격 확대",
                "summary": "요약2",
                "severity": "CRITICAL",
                "locations": ["Red Sea", "Bab el-Mandeb Strait"],
                "corridors": [],
                "keywords": [],
                "source_candidate_ids": ["C2"],
                "evidence": [{"article_id": "A2", "url": "https://x/2"}],
                "reactivated": False,
            },
            {
                "event_id": "MIREG-CCCC3333",
                "status": "RESOLVED",
                "first_seen": "2026-06-01",
                "last_seen": "2026-06-20",
                "sighting_count": 1,
                "sighting_dates": ["2026-06-20"],
                "headline": "수에즈 혼잡",
                "summary": "",
                "severity": "LOW",
                "locations": ["Suez Canal"],
                "corridors": [],
                "keywords": [],
                "source_candidate_ids": [],
                "evidence": [],
                "reactivated": False,
            },
            {
                "event_id": "MIREG-DDDD4444",
                "status": "ACTIVE",
                "first_seen": "2026-07-18",
                "last_seen": "2026-07-18",
                "sighting_count": 1,
                "sighting_dates": ["2026-07-18"],
                "headline": "위치 없는 소문",
                "summary": "",
                "severity": "LOW",
                "locations": [],
                "corridors": [],
                "keywords": [],
                "source_candidate_ids": [],
                "evidence": [],
                "reactivated": False,
            },
        ],
    }


@pytest.fixture()
def registry_file(tmp_path, monkeypatch):
    path = tmp_path / "mi_event_registry.json"
    path.write_text(json.dumps(_registry_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("MI_EVENT_REGISTRY_FILE", str(path))
    return path


# ---------- map-zones ----------

def test_map_zones_active_only_with_resolution(registry_file):
    zones = reg.map_zones()
    ids = {z["event_id"] for z in zones}
    # ACTIVE + IMPROVING + locations 있는 것만
    assert ids == {"MIREG-AAAA1111", "MIREG-BBBB2222"}
    red = next(z for z in zones if z["event_id"] == "MIREG-AAAA1111")
    assert red["locations"][0]["code"] == "RED_SEA"
    assert red["locations"][0]["lat"] and red["locations"][0]["radius_km"]


def test_map_zones_empty_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_EVENT_REGISTRY_FILE", str(tmp_path / "nope.json"))
    assert reg.map_zones() == []


def test_api_map_zones(registry_file):
    client = TestClient(app)
    resp = client.get("/api/mi/registry/map-zones")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------- review ----------

VALID_ANSWER = json.dumps(
    {
        "reviews": [
            {
                "event_id": "MIREG-AAAA1111",
                "suggested_status": "IMPROVING",
                "suggested_severity": "MEDIUM",
                "merge_with": None,
                "reason": "최근 목격 감소",
            },
            {
                "event_id": "MIREG-BBBB2222",
                "suggested_status": "ACTIVE",
                "suggested_severity": "CRITICAL",
                "merge_with": "MIREG-AAAA1111",
                "reason": "동일 사건으로 병합 제안",
            },
            {
                "event_id": "MIREG-HALLUCINATED",
                "suggested_status": "ACTIVE",
                "suggested_severity": "LOW",
                "merge_with": None,
                "reason": "없는 id",
            },
        ],
        "notes": "전체 요약",
    }
)


def _set_actify_env(monkeypatch):
    monkeypatch.setenv("ACTIFY_BASE_URL", "http://fake")
    monkeypatch.setenv("ACTIFY_API_KEY", "fake")
    monkeypatch.setenv("ACTIFY_USER", "tester")


def test_review_success_filters_unknown_ids(registry_file, monkeypatch):
    _set_actify_env(monkeypatch)
    monkeypatch.setattr(
        rev.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": VALID_ANSWER, "conversation_id": ""}
        )(),
    )
    result = rev.generate_registry_review()
    assert result["notes"] == "전체 요약"
    ids = {r["event_id"] for r in result["reviews"]}
    assert ids == {"MIREG-AAAA1111", "MIREG-BBBB2222"}  # 환각 id 제거
    merge = next(r for r in result["reviews"] if r["event_id"] == "MIREG-BBBB2222")
    assert merge["merge_with"] == "MIREG-AAAA1111"


def test_review_not_configured(monkeypatch):
    for key in ("ACTIFY_BASE_URL", "ACTIFY_API_KEY", "ACTIFY_USER"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(rev.ActifyNotConfiguredError):
        rev.generate_registry_review()


def test_review_broken_response(registry_file, monkeypatch):
    _set_actify_env(monkeypatch)
    monkeypatch.setattr(
        rev.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": "not json", "conversation_id": ""}
        )(),
    )
    with pytest.raises(RuntimeError):
        rev.generate_registry_review()


def test_api_review_503(monkeypatch):
    for key in ("ACTIFY_BASE_URL", "ACTIFY_API_KEY", "ACTIFY_USER"):
        monkeypatch.delenv(key, raising=False)
    client = TestClient(app)
    assert client.post("/api/mi/registry/review").status_code == 503


# ---------- apply ----------

def test_apply_status_and_severity(registry_file):
    result = reg.apply_proposal("MIREG-AAAA1111", status="IMPROVING", severity="MEDIUM")
    assert result["status"] == "IMPROVING"
    assert result["severity"] == "MEDIUM"
    with pytest.raises(KeyError):
        reg.apply_proposal("MIREG-NOPE", status="ACTIVE")
    with pytest.raises(ValueError):
        reg.apply_proposal("MIREG-AAAA1111", status="WRONG")


def test_apply_merge(registry_file):
    result = reg.apply_proposal("MIREG-BBBB2222", merge_with="MIREG-AAAA1111")
    assert result["first_seen"] == "2026-07-01"
    assert result["last_seen"] == "2026-07-19"
    assert result["sighting_count"] == 6
    assert set(result["source_candidate_ids"]) == {"C1", "C2"}
    assert "MIREG-AAAA1111" in result["merged_from"]
    # 병합된 이벤트 제거
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    ids = {e["event_id"] for e in data["events"]}
    assert "MIREG-AAAA1111" not in ids
    assert "MIREG-BBBB2222" in ids


def test_api_apply(registry_file):
    client = TestClient(app)
    resp = client.post(
        "/api/mi/registry/apply",
        json={"event_id": "MIREG-AAAA1111", "suggested_status": "IMPROVING"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IMPROVING"
    assert client.post(
        "/api/mi/registry/apply", json={"event_id": "MIREG-NOPE"}
    ).status_code == 404
