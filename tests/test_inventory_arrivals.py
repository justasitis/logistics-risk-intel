"""B-LAP 품목 도착 집계(inventory_arrivals) + params 병합 + API 테스트.

외부 호출(fetch_bl_info/fetch_bl_history_for_transports)은 monkeypatch로 대체.
"""
import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api_server import app
from backend.app.api.routes import inventory as inventory_route
from backend.app.services import inventory_arrivals

# TestClient는 실제 네트워크가 아니라 앱 낸부(ASGI)로만 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


def _info_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # T1: 같은 품목 2행 → 합산 150
            {"cmpy_cd": "SKO", "plnt_cd": "P1", "trpr_no": "T1", "item_cd": "162-00058A",
             "item_nm": "양극재", "dlvy_qty": 100, "dlvy_unit": "EA", "hbl_no": "HBL-1"},
            {"cmpy_cd": "SKO", "plnt_cd": "P1", "trpr_no": "T1", "item_cd": "162-00058A",
             "item_nm": "양극재", "dlvy_qty": 50, "dlvy_unit": "EA", "hbl_no": "HBL-1"},
            # T2: hbl 없음 → shipment_id는 trpr_no
            {"cmpy_cd": "SKO", "plnt_cd": "P1", "trpr_no": "T2", "item_cd": "162-00058A",
             "item_nm": "양극재", "dlvy_qty": 200, "dlvy_unit": "EA", "hbl_no": ""},
            # T3: metrics에 없는(비활성) 운송 → 제외
            {"cmpy_cd": "SKO", "plnt_cd": "P1", "trpr_no": "T3", "item_cd": "999-00000A",
             "item_nm": "기타", "dlvy_qty": 10, "dlvy_unit": "EA", "hbl_no": "HBL-3"},
        ]
    )


def _metrics_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"transport_key": "SKO|P1|T1", "trpr_no": "T1", "hbl_no": "HBL-1",
             "vessel_name": "V1", "eta_initial": "2026-08-01", "eta_current": "2026-08-10"},
            {"transport_key": "SKO|P1|T2", "trpr_no": "T2", "hbl_no": "",
             "vessel_name": "V2", "eta_initial": None, "eta_current": "2026-08-05"},
        ]
    )


def test_aggregate_item_arrivals():
    items = inventory_arrivals.aggregate_item_arrivals(_info_df(), _metrics_df())
    assert len(items) == 1
    item = items[0]
    assert item["item_id"] == "162-00058A"
    assert item["name"] == "양극재"
    assert item["unit"] == "EA"
    by_id = {s["shipment_id"]: s for s in item["shipments"]}
    assert set(by_id) == {"HBL-1", "T2"}
    # 동일 선적 내 동일 품목 합산
    assert by_id["HBL-1"]["qty"] == 150
    assert by_id["HBL-1"]["eta_plan"] == "2026-08-01"
    assert by_id["HBL-1"]["eta_current"] == "2026-08-10"
    # eta_initial 없으면 current로 대체
    assert by_id["T2"]["eta_plan"] == "2026-08-05"
    assert by_id["T2"]["qty"] == 200


def test_aggregate_excludes_eta_missing():
    metrics = pd.DataFrame(
        [{"transport_key": "SKO|P1|T1", "hbl_no": "HBL-1",
          "eta_initial": None, "eta_current": None}]
    )
    items = inventory_arrivals.aggregate_item_arrivals(_info_df(), metrics)
    assert items == []


def test_fetch_item_arrivals_pipeline(monkeypatch):
    monkeypatch.setattr(
        inventory_arrivals, "fetch_bl_info", lambda **kwargs: _info_df()
    )
    monkeypatch.setattr(
        inventory_arrivals,
        "fetch_bl_history_for_transports",
        lambda keys, **kwargs: pd.DataFrame(
            [
                {"cmpy_cd": "SKO", "plnt_cd": "P1", "trpr_no": "T1", "his_type": "ETA",
                 "fr_date": None, "to_date": "2026-08-01", "ins_datetime": "2026-07-01"},
                {"cmpy_cd": "SKO", "plnt_cd": "P1", "trpr_no": "T2", "his_type": "ETA",
                 "fr_date": None, "to_date": "2026-08-05", "ins_datetime": "2026-07-01"},
            ]
        ),
    )
    items = inventory_arrivals.fetch_item_arrivals()
    assert [i["item_id"] for i in items] == ["162-00058A"]
    by_id = {s["shipment_id"]: s for s in items[0]["shipments"]}
    assert by_id["HBL-1"]["qty"] == 150
    assert by_id["T2"]["qty"] == 200


# ---------- API (라우터의 집계 함수/params 경로 monkeypatch) ----------

FAKE_ARRIVALS = [
    {
        "item_id": "162-00058A",
        "name": "양극재",
        "unit": "EA",
        "shipments": [
            {"shipment_id": "HBL-1", "vessel_name": "V1", "qty": 150,
             "eta_plan": "2030-01-10", "eta_current": "2030-01-20"}
        ],
    },
    {
        "item_id": "162-99999A",
        "name": "기준값 없는 품목",
        "unit": "EA",
        "shipments": [
            {"shipment_id": "HBL-9", "vessel_name": "V9", "qty": 300,
             "eta_plan": "2030-02-01", "eta_current": "2030-02-01"}
        ],
    },
]


@pytest.fixture()
def blap_items(monkeypatch, tmp_path):
    monkeypatch.setattr(
        inventory_arrivals, "fetch_item_arrivals", lambda: FAKE_ARRIVALS
    )
    params_path = tmp_path / "params.json"
    params_path.write_text(
        json.dumps(
            {
                "162-00058A": {
                    "daily_usage": 100,
                    "on_hand_units": 1200,
                    "min_level_units": 500,
                    "destination": "유럽 공장",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(inventory_route, "STOCK_PARAMS_PATH", params_path)
    return TestClient(app)


def test_api_items_blap_with_params_merge(blap_items):
    resp = blap_items.get("/api/inventory/items")
    assert resp.status_code == 200
    items = {i["item_id"]: i for i in resp.json()["items"]}
    with_params = items["162-00058A"]
    assert with_params["source"] == "blap"
    assert with_params["params_missing"] is False
    assert with_params["daily_usage"] == 100
    assert with_params["on_hand_units"] == 1200
    assert with_params["min_level_units"] == 500
    assert with_params["destination"] == "유럽 공장"

    missing = items["162-99999A"]
    assert missing["params_missing"] is True
    assert missing["daily_usage"] == inventory_route.ASSUMED_DAILY_USAGE


def test_api_simulate_params_missing_warning(blap_items):
    resp = blap_items.post(
        "/api/inventory/simulate", json={"item_id": "162-99999A"}
    )
    assert resp.status_code == 200
    assert resp.json()["warning"] == inventory_route.PARAMS_WARNING

    resp = blap_items.post(
        "/api/inventory/simulate", json={"item_id": "162-00058A"}
    )
    assert resp.status_code == 200
    assert "warning" not in resp.json()


@pytest.mark.skip(
    reason="재고(L2 수급 영향) 기능 미사용. fallback 대상인 샘플 품목 마스터 "
    "backend/data/inventory_items.json이 git 미추적(.gitignore: backend/data/*.json)이라 "
    "새 클론에서 항상 404. 기능 재개 시 해제"
)
def test_api_fallback_to_sample_on_blap_failure(monkeypatch):
    def _raise():
        raise RuntimeError("B-LAP down")

    monkeypatch.setattr(inventory_arrivals, "fetch_item_arrivals", _raise)
    client = TestClient(app)
    resp = client.get("/api/inventory/items")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert all(i["source"] == "sample" for i in items)
