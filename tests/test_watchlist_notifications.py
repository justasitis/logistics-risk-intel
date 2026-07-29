"""관심화물(watchlist) + 알림 feed 테스트."""
import httpx
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from backend.app.services import watchlist_store

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


@pytest.fixture()
def watch_dir(tmp_path, monkeypatch):
    directory = tmp_path / "watchlist"
    monkeypatch.setenv("WATCHLIST_DIR", str(directory))
    return directory


# ---------- watchlist 저장소 ----------

def test_add_dedupe_remove(watch_dir):
    item = watchlist_store.add("HBL-1", "유럽행", username="alice")
    assert item["type"] == "hbl" and item["label"] == "유럽행"
    # 중복 무시
    again = watchlist_store.add("HBL-1", "다른 라벨", username="alice")
    assert again["label"] == "유럽행"
    assert len(watchlist_store.load("alice")["items"]) == 1

    assert watchlist_store.remove("HBL-1", username="alice") is True
    assert watchlist_store.remove("HBL-1", username="alice") is False
    assert watchlist_store.load("alice")["items"] == []


def test_user_separation(watch_dir):
    watchlist_store.add("HBL-1", username="alice")
    watchlist_store.add("HBL-2", username="bob")
    assert [i["id"] for i in watchlist_store.load("alice")["items"]] == ["HBL-1"]
    assert [i["id"] for i in watchlist_store.load("bob")["items"]] == ["HBL-2"]
    assert (watch_dir / "watchlist_alice.json").exists()
    assert (watch_dir / "watchlist_bob.json").exists()


def test_add_empty_id_422(watch_dir):
    with pytest.raises(ValueError):
        watchlist_store.add("  ", username="alice")


# ---------- API ----------

def test_api_watchlist_crud(watch_dir, monkeypatch):
    monkeypatch.setenv("USERNAME", "alice")
    client = TestClient(app)
    assert client.get("/api/watchlist").json() == {"items": []}
    resp = client.post("/api/watchlist", json={"id": "HBL-9", "label": "북미행"})
    assert resp.status_code == 201
    assert len(client.get("/api/watchlist").json()["items"]) == 1
    assert client.delete("/api/watchlist/HBL-9").status_code == 200
    assert client.delete("/api/watchlist/HBL-9").status_code == 404


FAKE_ROW = {
    "hbl_no": "HBL-1",
    "delivery_req_breach_days": 9,
    "anomaly_signals": ["REPEATED_ETA_DELAY"],
    "severity": "CRITICAL",
}


def test_notifications_feed_direct_query(watch_dir, monkeypatch):
    monkeypatch.setenv("USERNAME", "alice")
    watchlist_store.add("HBL-1", username="alice")  # breach + signal
    watchlist_store.add("HBL-2", username="alice")  # 정상
    watchlist_store.add("HBL-9", username="alice")  # 미존재
    # overview 캐시 없음 + 직접 조회 경로만 사용
    monkeypatch.setattr(api_server, "_cached_overview_transports", lambda: {})
    called = {}

    def _fake_enriched(hbl_nos):
        called["hbl_nos"] = hbl_nos
        return {"HBL-1": FAKE_ROW, "HBL-2": {**FAKE_ROW, "hbl_no": "HBL-2",
                                             "delivery_req_breach_days": 0,
                                             "anomaly_signals": [],
                                             "severity": "NORMAL"}}

    monkeypatch.setattr(api_server, "_enriched_transports_by_hbl", _fake_enriched)

    client = TestClient(app)
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert called["hbl_nos"] == ["HBL-1", "HBL-2", "HBL-9"]
    items = {i["hbl_no"]: i for i in body["items"]}

    hbl1 = items["HBL-1"]["alerts"]
    types = {a["type"] for a in hbl1}
    assert types == {"DELIVERY_REQ_BREACH", "SIGNAL"}
    breach = next(a for a in hbl1 if a["type"] == "DELIVERY_REQ_BREACH")
    assert breach["severity"] == "HIGH" and breach["value"] == 9
    assert "납기 초과 +9일" in breach["message"]

    assert items["HBL-2"]["alerts"] == []
    not_found = items["HBL-9"]["alerts"][0]
    assert not_found["type"] == "NOT_FOUND"
    assert not_found["severity"] == "LOW"


def test_notifications_uses_overview_cache_when_present(watch_dir, monkeypatch):
    monkeypatch.setenv("USERNAME", "alice")
    watchlist_store.add("HBL-1", username="alice")
    monkeypatch.setattr(
        api_server, "_cached_overview_transports", lambda: {"HBL-1": FAKE_ROW}
    )

    def _boom(hbl_nos):
        raise AssertionError("캐시 히트 시 직접 조회를 호출하면 안 됨")

    monkeypatch.setattr(api_server, "_enriched_transports_by_hbl", _boom)
    client = TestClient(app)
    body = client.get("/api/notifications").json()
    assert body["cache_hit"] is True
    assert {a["type"] for a in body["items"][0]["alerts"]} == {
        "DELIVERY_REQ_BREACH",
        "SIGNAL",
    }


def test_notifications_empty_watchlist(watch_dir, monkeypatch):
    monkeypatch.setenv("USERNAME", "alice")

    def _boom(hbl_nos):
        raise AssertionError("watchlist가 비면 조회하지 않아야 함")

    monkeypatch.setattr(api_server, "_enriched_transports_by_hbl", _boom)
    client = TestClient(app)
    body = client.get("/api/notifications").json()
    assert body["items"] == []
