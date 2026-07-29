"""신규 API 2건 테스트: /api/routes/master, /api/report/freight-indices."""
from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from backend.app.core import marinesia_settings

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단을 되돌린다.
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


@pytest.fixture
def client():
    return TestClient(app)


def _bl_info_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _info_row(**overrides):
    row = {
        "cmpy_nm": "SKO",
        "plnt_nm": "울산1",
        "lsp_nm": "LSP-A",
        "bsns_ccd_nm": "완성차",
        "trpr_mode": "100",
        "trpr_no": "TR1",
        "dprt": "KRPUS",
        "dprt_nm": "부산",
        "arvl": "SIKOP",
        "arvl_nm": "코페르",
        "to_stlc_cd": "SIKOP01",
        "to_stlc_nm": "코페르 물류센터",
    }
    row.update(overrides)
    return row


@pytest.fixture
def mock_bl_info(monkeypatch):
    captured = {}

    def _install(df: pd.DataFrame):
        def _fake(**kwargs):
            captured.update(kwargs)
            return df

        monkeypatch.setattr(api_server, "fetch_bl_info", _fake)

    _install.captured = captured
    return _install


# ---------- ① /api/routes/master ----------

class TestRouteMaster:
    def test_grouping_and_shipment_count(self, client, mock_bl_info):
        mock_bl_info(_bl_info_df([
            # 같은 조합, 같은 운송번호(PO 2라인) → 1건
            _info_row(trpr_no="TR1", po_no="PO1"),
            _info_row(trpr_no="TR1", po_no="PO2"),
            # 같은 조합, 다른 운송번호 → +1
            _info_row(trpr_no="TR2"),
            # 다른 POD 조합
            _info_row(trpr_no="TR3", arvl="DEHAM", arvl_nm="함부르크"),
        ]))
        response = client.get("/api/routes/master")
        assert response.status_code == 200
        body = response.json()
        assert body["total_rows"] == 2
        assert body["truncated"] is False
        # 건수 내림차순: TR1+TR2 조합(2건)이 먼저
        first, second = body["rows"]
        assert first["shipment_count"] == 2
        assert second["shipment_count"] == 1
        # 필수 필드는 dims 없이도 항상 포함
        for field in ("dprt", "dprt_nm", "arvl", "arvl_nm",
                      "to_stlc_cd", "to_stlc_nm"):
            assert field in first
        assert first["dprt"] == "KRPUS"
        # dims 미선택 필드는 응답에 없다
        assert "cmpy_nm" not in first
        assert "trpr_mode" not in first

    def test_dims_included_and_trpr_mode_label(self, client, mock_bl_info):
        mock_bl_info(_bl_info_df([
            _info_row(trpr_no="TR1", trpr_mode="100"),
            _info_row(trpr_no="TR2", trpr_mode="999"),
        ]))
        response = client.get(
            "/api/routes/master",
            params=[("dims", "cmpy_nm"), ("dims", "trpr_mode")],
        )
        assert response.status_code == 200
        rows = response.json()["rows"]
        assert rows[0]["cmpy_nm"] == "SKO"
        labels = {row["trpr_mode"]: row["trpr_mode_label"] for row in rows}
        assert labels["100"] == "해상"
        assert labels["999"] == "999"  # 미등록 코드는 코드 그대로

    def test_company_filter_passed_as_cmpy_nm(self, client, mock_bl_info):
        mock_bl_info(_bl_info_df([_info_row()]))
        response = client.get(
            "/api/routes/master",
            params=[("companies", "SKO"), ("companies", "SKBA")],
        )
        assert response.status_code == 200
        assert mock_bl_info.captured["companies"] == ["SKO", "SKBA"]

    def test_invalid_dims_rejected(self, client, mock_bl_info):
        mock_bl_info(_bl_info_df([_info_row()]))
        response = client.get(
            "/api/routes/master", params=[("dims", "hbl_no")],
        )
        assert response.status_code == 422

    def test_truncation(self, client, mock_bl_info, monkeypatch):
        monkeypatch.setattr(api_server, "ROUTE_MASTER_MAX_ROWS", 500)
        rows = [
            _info_row(trpr_no=f"TR{i}", arvl=f"P{i:03d}XX")
            for i in range(501)
        ]
        mock_bl_info(_bl_info_df(rows))
        response = client.get("/api/routes/master")
        body = response.json()
        assert body["total_rows"] == 501
        assert body["truncated"] is True
        assert len(body["rows"]) == 500

    def test_empty_result(self, client, mock_bl_info):
        mock_bl_info(pd.DataFrame())
        response = client.get("/api/routes/master")
        body = response.json()
        assert body["total_rows"] == 0
        assert body["rows"] == []

    def test_datalake_failure_is_502(self, client, monkeypatch):
        def _raise(**kwargs):
            raise RuntimeError("데이터레이크 연결 실패")

        monkeypatch.setattr(api_server, "fetch_bl_info", _raise)
        response = client.get("/api/routes/master")
        assert response.status_code == 502


# ---------- ② /api/report/freight-indices ----------

FREIGHT_PAYLOAD = {
    "scfi": [{"date": "2026-07-03", "value": 1550.5}],
    "kcci": [{"date": "2026-07-03", "value": 1234}],
    "kcci_usec": [{"date": "2026-07-03", "value": 4200}],
    "kcci_med": [{"date": "2026-07-03", "value": 3900}],
    "unknown_series": [{"date": "2026-07-03", "value": 1}],
}


@pytest.fixture
def sharepoint_root(tmp_path, monkeypatch):
    root = tmp_path / "LogisticsRisk"
    monkeypatch.setenv("MARINESIA_SHAREPOINT_ROOT", str(root))
    marinesia_settings.get_marinesia_settings.cache_clear()
    yield root
    marinesia_settings.get_marinesia_settings.cache_clear()


def _write_freight(root, payload) -> None:
    path = root / "MI" / "freight_indices" / "freight_indices.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )


class TestFreightIndices:
    def test_series_parsing_and_labels(self, client, sharepoint_root):
        _write_freight(sharepoint_root, FREIGHT_PAYLOAD)
        response = client.get("/api/report/freight-indices")
        assert response.status_code == 200
        body = response.json()
        assert body["source_file"].endswith("freight_indices.json")
        by_key = {s["key"]: s for s in body["series"]}
        assert set(by_key) == {"scfi", "kcci", "kcci_usec", "kcci_med"}
        assert by_key["kcci_usec"]["label"] == "KCCI 북미 동안 (USD/40')"
        assert by_key["kcci_med"]["label"] == "KCCI 지중해 (USD/40')"
        assert by_key["scfi"]["label"] == "SCFI"
        assert by_key["kcci"]["label"] == "KCCI 종합"
        assert by_key["scfi"]["points"] == [
            {"date": "2026-07-03", "value": 1550.5}
        ]

    def test_partial_series_ok(self, client, sharepoint_root):
        _write_freight(sharepoint_root, {"scfi": [{"date": "d", "value": 1}]})
        response = client.get("/api/report/freight-indices")
        keys = [s["key"] for s in response.json()["series"]]
        assert keys == ["scfi"]

    def test_missing_file_is_404(self, client, sharepoint_root):
        # sharepoint_root 아래 파일 없음 + backend/data 폴�도 없음 확인
        fallback = (
            api_server._Path(api_server.__file__).resolve().parent
            / "backend" / "data" / "freight_indices.json"
        )
        if fallback.exists():
            pytest.skip("backend/data 폴� 파일이 존재해 404 검증 불가")
        response = client.get("/api/report/freight-indices")
        assert response.status_code == 404

    def test_broken_json_is_502(self, client, sharepoint_root):
        _write_freight(sharepoint_root, "{ broken")
        assert client.get("/api/report/freight-indices").status_code == 502

    def test_non_object_is_502(self, client, sharepoint_root):
        _write_freight(sharepoint_root, [1, 2, 3])
        assert client.get("/api/report/freight-indices").status_code == 502

    def test_series_not_list_is_502(self, client, sharepoint_root):
        _write_freight(sharepoint_root, {"scfi": {"date": "d"}})
        assert client.get("/api/report/freight-indices").status_code == 502

    def test_point_missing_value_is_502(self, client, sharepoint_root):
        _write_freight(sharepoint_root, {"scfi": [{"date": "d"}]})
        assert client.get("/api/report/freight-indices").status_code == 502

    def test_non_numeric_value_is_502(self, client, sharepoint_root):
        _write_freight(
            sharepoint_root, {"scfi": [{"date": "d", "value": "abc"}]},
        )
        assert client.get("/api/report/freight-indices").status_code == 502
