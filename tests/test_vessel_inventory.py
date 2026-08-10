"""GET /api/vessels/inventory 선박 인벤토리 집계 테스트 (가짜 DataFrame, 외부 호출 없음)."""
from datetime import date, timedelta

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


@pytest.fixture(autouse=True)
def _clear_cache():
    api_server._CACHE.clear()
    yield
    api_server._CACHE.clear()


TODAY = date.today()
FUTURE_ETA = (TODAY + timedelta(days=20)).isoformat()
LATER_ETA = (TODAY + timedelta(days=45)).isoformat()


def _info_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(trpr_no, vessel_nm, **kw):
    base = {
        "cmpy_cd": "S000",
        "plnt_cd": "P1",
        "trpr_no": trpr_no,
        "vessel_nm": vessel_nm,
        "dprt": "KRPUS",
        "dprt_nm": "BUSAN",
        "arvl": "SIKOP",
        "arvl_nm": "KOPER",
        "eta": "",
        "eta_date": FUTURE_ETA,
        "ata": "",
        "dlvy_ata": "",
        "cmpl_yn": "N",
    }
    base.update(kw)
    return base


def _client(monkeypatch, info_df):
    monkeypatch.setattr(api_server, "fetch_bl_info", lambda **_: info_df)
    return TestClient(app)


class TestVesselInventory:
    def test_groups_by_vessel_and_counts_unique_trpr(self, monkeypatch):
        info_df = _info_df([
            _row("T001", "VSL ALPHA"),
            # 같은 trpr_no가 다른 법인 행으로 중복돼도 1건으로 센다.
            _row("T001", "VSL ALPHA", cmpy_cd="S100"),
            _row("T002", "VSL ALPHA"),
            _row("T003", "VSL BETA"),
        ])
        client = _client(monkeypatch, info_df)

        response = client.get("/api/vessels/inventory")
        assert response.status_code == 200
        body = response.json()

        # transport_count는 스냅샷 운송 수 (T001이 법인 2곳에 걸려 4행).
        assert body["transport_count"] == 4
        assert body["cache_hit"] is False
        assert [v["vessel_name"] for v in body["vessels"]] == [
            "VSL ALPHA", "VSL BETA",
        ]
        alpha = body["vessels"][0]
        assert alpha["shipment_count"] == 2
        assert alpha["trpr_nos"] == ["T001", "T002"]
        assert alpha["lanes"] == ["BUSAN–KOPER"]
        assert alpha["latest_eta"] is not None

    def test_trpr_nos_capped_at_five(self, monkeypatch):
        info_df = _info_df([
            _row(f"T{i:03d}", "VSL GAMMA") for i in range(7)
        ])
        client = _client(monkeypatch, info_df)

        body = client.get("/api/vessels/inventory").json()
        vessel = body["vessels"][0]
        assert vessel["shipment_count"] == 7
        assert len(vessel["trpr_nos"]) == 5

    def test_placeholder_and_blank_vessel_names_excluded(self, monkeypatch):
        info_df = _info_df([
            _row("T001", "TBA"),
            _row("T002", "tbd"),
            _row("T003", ""),
            _row("T004", "선박미정"),
            _row("T005", "X"),  # 2자 미만 제외
            _row("T006", "VSL REAL"),
        ])
        client = _client(monkeypatch, info_df)

        body = client.get("/api/vessels/inventory").json()
        assert [v["vessel_name"] for v in body["vessels"]] == ["VSL REAL"]
        # 플레이스홀더 운송은 transport_count에는 포함된다 (스냅샷 기준).
        assert body["transport_count"] == 6

    def test_latest_eta_is_max(self, monkeypatch):
        info_df = _info_df([
            _row("T001", "VSL ETA", eta_date=FUTURE_ETA),
            _row("T002", "VSL ETA", eta_date=LATER_ETA),
        ])
        client = _client(monkeypatch, info_df)

        body = client.get("/api/vessels/inventory").json()
        vessel = body["vessels"][0]
        assert vessel["latest_eta"].startswith(LATER_ETA[:10])

    def test_vessel_name_trimmed(self, monkeypatch):
        info_df = _info_df([
            _row("T001", "  VSL TRIM  "),
        ])
        client = _client(monkeypatch, info_df)

        body = client.get("/api/vessels/inventory").json()
        assert body["vessels"][0]["vessel_name"] == "VSL TRIM"

    def test_empty_result(self, monkeypatch):
        client = _client(monkeypatch, pd.DataFrame())

        response = client.get("/api/vessels/inventory")
        assert response.status_code == 200
        body = response.json()
        assert body["vessels"] == []
        assert body["transport_count"] == 0

    def test_cache_hit_and_refresh(self, monkeypatch):
        info_df = _info_df([_row("T001", "VSL CACHE")])
        client = _client(monkeypatch, info_df)

        first = client.get("/api/vessels/inventory").json()
        assert first["cache_hit"] is False
        second = client.get("/api/vessels/inventory").json()
        assert second["cache_hit"] is True
        refreshed = client.get(
            "/api/vessels/inventory", params={"refresh": "true"},
        ).json()
        assert refreshed["cache_hit"] is False

    def test_runtime_error_returns_generic_502(self, monkeypatch):
        def _raise(**_):
            raise RuntimeError("denodo internal secret detail")

        monkeypatch.setattr(api_server, "fetch_bl_info", _raise)
        client = TestClient(app)

        response = client.get("/api/vessels/inventory")
        assert response.status_code == 502
        # 남부 예외 문자열은 응답에 노출하지 않는다.
        assert "denodo" not in response.json()["detail"]
