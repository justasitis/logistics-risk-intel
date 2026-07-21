"""L2 수급 시뮬레이션: 순수 함수 단위 테스트 + API 테스트 (v2에서 백포트)."""
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from api_server import app
from backend.app.services import inventory_sim

# conftest의 외부 HTTP 차단은 httpx.Client.request를 패치한다.
# TestClient는 실제 네트워크가 아니라 앱 낸부(ASGI)로만 호출하므로 원래 구현을 복원한다.
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)

TODAY = date(2026, 7, 19)


def _iso(d: date) -> str:
    return d.isoformat()


def _item(**overrides):
    item = {
        "item_id": "TEST-ITEM",
        "name": "테스트 품목",
        "unit": "units",
        "daily_usage": 100,
        "on_hand_units": 1000,
        "min_level_units": 500,
        "shipments": [
            {
                "shipment_id": "S1",
                "vessel_name": "V",
                "qty": 800,
                "eta_plan": _iso(TODAY + timedelta(days=5)),
                "eta_current": _iso(TODAY + timedelta(days=12)),
            }
        ],
    }
    item.update(overrides)
    return item


# ---------- 순수 함수 ----------

def test_plan_series_reflects_arrival():
    res = inventory_sim.simulate(_item(), today=TODAY, horizon_days=14)
    plan = res["series_plan"]
    assert len(plan) == 15
    assert plan[4]["balance"] == 1000 - 400
    assert plan[5]["balance"] == 1000 + 800 - 500
    assert plan[0]["date"] == _iso(TODAY)


def test_current_series_applies_delay():
    res = inventory_sim.simulate(_item(), today=TODAY, horizon_days=14)
    cur = res["series_current"]
    assert cur[11]["balance"] == 1000 - 1100
    assert cur[12]["balance"] == 1000 + 800 - 1200


def test_extra_delay_pushes_arrival_beyond_horizon():
    res = inventory_sim.simulate(_item(), extra_delay_days=3, today=TODAY, horizon_days=14)
    m = res["metrics"]
    assert res["series_current"][14]["balance"] == 1000 - 1400
    assert m["max_delay_days"] == 7 + 3
    assert m["gap_qty"] == 400
    assert m["risk_level"] == "STOCKOUT"


def test_stockout_window_and_gap():
    res = inventory_sim.simulate(_item(), today=TODAY, horizon_days=14)
    m = res["metrics"]
    assert m["stockout_windows"] == [
        {
            "start": _iso(TODAY + timedelta(days=11)),
            "end": _iso(TODAY + timedelta(days=11)),
            "days": 1,
        }
    ]
    assert m["gap_qty"] == 100
    assert m["min_balance"] == -100
    assert m["risk_level"] == "STOCKOUT"
    types = {a["type"] for a in res["actions"]}
    assert types == {"AIR_UPGRADE", "PULL_FORWARD_ORDER"}


def test_below_min_windows():
    res = inventory_sim.simulate(_item(shipments=[]), today=TODAY, horizon_days=14)
    m = res["metrics"]
    assert m["below_min_windows"] == [
        {
            "start": _iso(TODAY + timedelta(days=6)),
            "end": _iso(TODAY + timedelta(days=14)),
            "days": 9,
        }
    ]
    assert m["max_delay_days"] == 0


def test_risk_level_shortage_risk():
    res = inventory_sim.simulate(_item(shipments=[]), today=TODAY, horizon_days=8)
    m = res["metrics"]
    assert m["risk_level"] == "SHORTAGE_RISK"
    assert m["stockout_windows"] == []
    assert m["gap_qty"] == 0


def test_risk_level_watch():
    res = inventory_sim.simulate(_item(), today=TODAY, horizon_days=4)
    assert res["metrics"]["min_balance"] == 600
    assert res["metrics"]["risk_level"] == "WATCH"


def test_risk_level_ok():
    res = inventory_sim.simulate(
        _item(on_hand_units=10000), today=TODAY, horizon_days=14
    )
    assert res["metrics"]["risk_level"] == "OK"


# ---------- API ----------

def test_api_items():
    client = TestClient(app)
    resp = client.get("/api/inventory/items")
    assert resp.status_code == 200
    ids = [i["item_id"] for i in resp.json()["items"]]
    assert ids == ["CELL-MAT-A", "CATHODE-B", "CELL-PROD-D", "ELECTROLYTE-E"]


def test_api_simulate_ok():
    client = TestClient(app)
    resp = client.post(
        "/api/inventory/simulate",
        json={"item_id": "CELL-MAT-A", "extra_delay_days": 0, "horizon_days": 45},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["item_id"] == "CELL-MAT-A"
    assert len(body["series_plan"]) == 46
    assert len(body["series_current"]) == 46
    m = body["metrics"]
    assert m["risk_level"] in inventory_sim.RISK_LEVELS
    assert isinstance(m["below_min_windows"], list)
    assert isinstance(body["actions"], list)


def test_api_simulate_unknown_item_404():
    client = TestClient(app)
    resp = client.post("/api/inventory/simulate", json={"item_id": "NOPE"})
    assert resp.status_code == 404


def test_api_simulate_range_422():
    client = TestClient(app)
    assert (
        client.post(
            "/api/inventory/simulate",
            json={"item_id": "CELL-MAT-A", "extra_delay_days": 61},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/inventory/simulate",
            json={"item_id": "CELL-MAT-A", "horizon_days": 10},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/inventory/simulate",
            json={"item_id": "CELL-MAT-A", "horizon_days": 121},
        ).status_code
        == 422
    )
