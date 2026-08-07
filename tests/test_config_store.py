"""설정 저장소(config_store)와 /api/config/* 엔드포인트 테스트.

conftest의 _isolate_config_dir fixture가 LRI_CONFIG_DIR을 임시 디렉터리로
고정하므로, 여기서 만드는 커스텀 설정은 실제 SharePoint 폴터를 건드리지 않는다.
"""
from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from services import config_store
from services.config_store import (
    load_config,
    reset_config,
    save_config,
    validate_config,
)

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request

ADMIN_USER = "so23132"  # REPORT_PUBLISH_USERS 기본값


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


@pytest.fixture
def client():
    return TestClient(app)


def _set_user(monkeypatch, username: str):
    monkeypatch.setattr(
        "backend.app.core.user_path.current_username", lambda: username,
    )


# ---------- 저장소 기본 동작 ----------


class TestConfigStore:
    def test_default_load_when_no_custom(self):
        """커스텀 파일이 없으면 repo 기본 파일을 읽는다."""
        data = load_config("route_groups")
        assert isinstance(data, dict)
        ids = [g["group_id"] for g in data["groups"]]
        assert "ADRIA_SUEZ" in ids
        assert config_store.source_of("route_groups") == "default"
        assert config_store.updated_at("route_groups") is None

    def test_save_then_custom_load(self):
        """save_config 후에는 커스텀 파일이 우선 적용된다."""
        custom = {"groups": [{"group_id": "X", "name": "x", "region": "r",
                              "arvl_codes": ["AAAA"]}]}
        save_config("route_groups", custom)
        assert load_config("route_groups") == custom
        assert config_store.source_of("route_groups") == "custom"
        assert config_store.updated_at("route_groups") is not None

    def test_reset_returns_to_default(self):
        """reset_config는 커스텀 파일을 지워 기본값으로 복귀한다."""
        save_config("gap_thresholds", {"warn_days": 9.9})
        assert reset_config("gap_thresholds") is True
        assert load_config("gap_thresholds")["warn_days"] == 5.0
        # 커스텀이 없는 상태에서 reset은 False
        assert reset_config("gap_thresholds") is False

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            load_config("no_such_key")

    def test_catalog_lists_seven_sections(self):
        sections = config_store.catalog()
        assert [s["key"] for s in sections] == [
            "route_groups",
            "location_master",
            "delay_thresholds",
            "gap_thresholds",
            "anomaly_thresholds",
            "companies",
            "carrier_inference",
        ]
        assert all(s["source"] == "default" for s in sections)
        kinds = {s["key"]: s["kind"] for s in sections}
        assert kinds["delay_thresholds"] == "thresholds"
        assert kinds["route_groups"] == "route_groups"


# ---------- 검증 ----------


class TestValidation:
    def test_route_groups_duplicate_group_id(self):
        with pytest.raises(ValueError, match="중복"):
            validate_config("route_groups", {"groups": [
                {"group_id": "A", "name": "a", "region": "r",
                 "arvl_codes": ["X"]},
                {"group_id": "A", "name": "b", "region": "r",
                 "arvl_codes": ["Y"]},
            ]})

    def test_route_groups_missing_field(self):
        with pytest.raises(ValueError, match="arvl_codes"):
            validate_config("route_groups", {"groups": [
                {"group_id": "A", "name": "a", "region": "r"},
            ]})

    def test_location_master_lat_range(self):
        with pytest.raises(ValueError, match="lat"):
            validate_config("location_master", {"KRPUS": {
                "name": "Busan", "location_type": "PORT",
                "lat": 91.0, "lon": 129.0, "default_radius_km": 100,
            }})

    def test_location_master_radius_positive(self):
        with pytest.raises(ValueError, match="default_radius_km"):
            validate_config("location_master", {"KRPUS": {
                "name": "Busan", "location_type": "PORT",
                "lat": 35.0, "lon": 129.0, "default_radius_km": 0,
            }})

    def test_delay_thresholds_coverage_range(self):
        with pytest.raises(ValueError, match="coverage_warn"):
            validate_config("delay_thresholds", {
                "iqr_tight": 2.0, "median_small_abs": 1.0,
                "median_late": 3.0, "iqr_volatile": 4.0,
                "tail_burst": 6.0, "min_sample": 10, "coverage_warn": 1.5,
            })

    def test_delay_thresholds_min_sample(self):
        with pytest.raises(ValueError, match="min_sample"):
            validate_config("delay_thresholds", {
                "iqr_tight": 2.0, "median_small_abs": 1.0,
                "median_late": 3.0, "iqr_volatile": 4.0,
                "tail_burst": 6.0, "min_sample": 0, "coverage_warn": 0.7,
            })

    def test_gap_thresholds_weeks_range(self):
        with pytest.raises(ValueError, match="weeks"):
            validate_config("gap_thresholds", {
                "warn_days": 5.0, "watch_consecutive": 3,
                "weeks": 20, "etd_lookback_days": 180,
            })

    def test_gap_thresholds_watch_consecutive(self):
        with pytest.raises(ValueError, match="watch_consecutive"):
            validate_config("gap_thresholds", {
                "warn_days": 5.0, "watch_consecutive": 1,
                "weeks": 8, "etd_lookback_days": 180,
            })

    def test_anomaly_thresholds_positive_int(self):
        with pytest.raises(ValueError, match="repeated_delay_count"):
            validate_config("anomaly_thresholds", {
                "repeated_delay_count": 0,
                "medium_delay_days": 3, "high_delay_days": 6,
                "critical_delay_days": 10, "lead_time_warning_days": 3,
                "lead_time_high_days": 6, "lead_time_critical_days": 10,
                "delivery_breach_medium_days": 3,
                "delivery_breach_high_days": 7,
                "delivery_breach_critical_days": 14,
            })

    def test_anomaly_thresholds_unknown_field(self):
        with pytest.raises(ValueError, match="알 수 없는 필드"):
            validate_config("anomaly_thresholds", {
                "repeated_delay_count": 2, "unknown_field": 1,
            })

    def test_companies_duplicate_code(self):
        with pytest.raises(ValueError, match="중복"):
            validate_config("companies", {"companies": [
                {"code": "SKO", "label": "a", "lap_code": "S000"},
                {"code": "sko", "label": "b", "lap_code": "S001"},
            ]})

    def test_companies_missing_lap_code(self):
        with pytest.raises(ValueError, match="lap_code"):
            validate_config("companies", {"companies": [
                {"code": "SKO", "label": "a"},
            ]})

    def test_carrier_inference_via_only_suez_cape(self):
        with pytest.raises(ValueError, match="SUEZ 또는 CAPE"):
            validate_config("carrier_inference", {
                "adria_arrival_ports": ["SIKOP"],
                "vessel_carrier_rules": [],
                "carrier_via_rules": [
                    {"carrier_cd": "MAEU",
                     "carrier_nm_contains": "MAERSK", "via": "PANAMA"},
                ],
            })

    def test_valid_defaults_pass(self):
        """repo 기본 파일 7개는 모두 검증을 통과해야 한다."""
        for key in config_store.CONFIG_SPECS:
            validate_config(key, load_config(key))


# ---------- API ----------


class TestConfigApi:
    def test_catalog_open_to_all(self, client):
        res = client.get("/api/config/catalog")
        assert res.status_code == 200
        assert len(res.json()["sections"]) == 7

    def test_get_section_open_to_all(self, client):
        res = client.get("/api/config/delay_thresholds")
        assert res.status_code == 200
        body = res.json()
        assert body["key"] == "delay_thresholds"
        assert body["source"] == "default"
        assert body["data"]["min_sample"] == 10

    def test_get_unknown_key_404(self, client):
        assert client.get("/api/config/nope").status_code == 404

    def test_put_forbidden_for_non_manager(self, client, monkeypatch):
        _set_user(monkeypatch, "viewer01")
        res = client.put(
            "/api/config/gap_thresholds",
            json={"data": {"warn_days": 7.0, "watch_consecutive": 3,
                           "weeks": 8, "etd_lookback_days": 180}},
        )
        assert res.status_code == 403

    def test_reset_forbidden_for_non_manager(self, client, monkeypatch):
        _set_user(monkeypatch, "viewer01")
        res = client.post("/api/config/gap_thresholds/reset")
        assert res.status_code == 403

    def test_put_invalid_returns_400_korean(self, client, monkeypatch):
        _set_user(monkeypatch, ADMIN_USER)
        res = client.put(
            "/api/config/gap_thresholds",
            json={"data": {"warn_days": -1, "watch_consecutive": 3,
                           "weeks": 8, "etd_lookback_days": 180}},
        )
        assert res.status_code == 400
        assert "warn_days" in res.json()["detail"]

    @pytest.mark.parametrize("key,invalid", [
        ("route_groups", {"groups": [{"group_id": "A"}]}),
        ("location_master", {"X": {"name": "x"}}),
        ("delay_thresholds", {"min_sample": 0}),
        ("gap_thresholds", {"weeks": 1}),
        ("anomaly_thresholds", {"repeated_delay_count": -2}),
        ("companies", {"companies": [{"code": "SKO"}]}),
        ("carrier_inference", {"adria_arrival_ports": []}),
    ])
    def test_put_invalid_each_key_400(self, client, monkeypatch, key, invalid):
        _set_user(monkeypatch, ADMIN_USER)
        res = client.put(f"/api/config/{key}", json={"data": invalid})
        assert res.status_code == 400
        assert res.json()["detail"]

    def test_put_ok_clears_cache_and_applies(self, client, monkeypatch):
        """권한 사용자 PUT → 200, 커스텀 적용, _CACHE 전체 클리어."""
        _set_user(monkeypatch, ADMIN_USER)
        api_server._CACHE["dummy|1"] = (0.0, {"x": 1})
        payload = {"warn_days": 7.5, "watch_consecutive": 4,
                   "weeks": 12, "etd_lookback_days": 200}
        res = client.put("/api/config/gap_thresholds",
                         json={"data": payload})
        assert res.status_code == 200
        assert res.json() == {"ok": True}
        assert api_server._CACHE == {}
        body = client.get("/api/config/gap_thresholds").json()
        assert body["source"] == "custom"
        assert body["updated_at"] is not None
        assert body["data"] == payload

    def test_reset_restores_default(self, client, monkeypatch):
        _set_user(monkeypatch, ADMIN_USER)
        client.put("/api/config/gap_thresholds",
                   json={"data": {"warn_days": 9.0, "watch_consecutive": 3,
                                  "weeks": 8, "etd_lookback_days": 180}})
        res = client.post("/api/config/gap_thresholds/reset")
        assert res.status_code == 200
        body = client.get("/api/config/gap_thresholds").json()
        assert body["source"] == "default"
        assert body["data"]["warn_days"] == 5.0


# ---------- 서비스 소비처 반영 ----------


class TestServiceIntegration:
    def test_delay_target_flag_drives_target_groups(self):
        """delay_target 플래그가 있는 그룹만 지연 분해 대상이 된다."""
        from services.delay_decomposition_service import (
            list_delay_groups,
            target_group_ids,
        )

        groups = [
            {"group_id": "A", "name": "a", "delay_target": True},
            {"group_id": "B", "name": "b"},
            {"group_id": "C", "name": "c", "delay_target": True},
        ]
        assert target_group_ids(groups) == ["A", "C"]
        assert [g["group_id"] for g in list_delay_groups(groups)] == ["A", "C"]

    def test_delay_target_fallback_to_constant(self):
        """플래그가 하나도 없으면 기존 TARGET_GROUP_IDS 상수로 폴터."""
        from services.delay_decomposition_service import (
            TARGET_GROUP_IDS,
            target_group_ids,
        )

        groups = [{"group_id": "US_EAST"}, {"group_id": "OTHER"}]
        assert target_group_ids(groups) == TARGET_GROUP_IDS

    def test_default_route_groups_flagged_six(self):
        """기본 route_groups 설정은 6개 해상 그룹에 delay_target이 있다."""
        from services import leadtime_report_service
        from services.delay_decomposition_service import (
            TARGET_GROUP_IDS,
            target_group_ids,
        )

        groups = leadtime_report_service.load_route_groups()
        assert target_group_ids(groups) == TARGET_GROUP_IDS

    def test_gap_thresholds_from_config(self):
        """커스텀 gap_thresholds가 compute 기본값에 반영된다."""
        from services import eta_ata_gap_service

        save_config("gap_thresholds", {
            "warn_days": 5.0, "watch_consecutive": 3,
            "weeks": 4, "etd_lookback_days": 180,
        })
        report = eta_ata_gap_service.compute_eta_ata_gap(
            pd.DataFrame(), today=pd.Timestamp("2026-08-07").date(),
        )
        assert report["params"]["weeks"] == 4

    def test_anomaly_thresholds_from_config(self):
        """커스텀 anomaly_thresholds가 evaluate 기본 규칙에 반영된다."""
        from services import anomaly_engine

        data = json.loads(json.dumps({
            "repeated_delay_count": 5,
            "medium_delay_days": 3, "high_delay_days": 6,
            "critical_delay_days": 10, "lead_time_warning_days": 3,
            "lead_time_high_days": 6, "lead_time_critical_days": 10,
            "delivery_breach_medium_days": 3,
            "delivery_breach_high_days": 7,
            "delivery_breach_critical_days": 14,
        }))
        save_config("anomaly_thresholds", data)
        rules = anomaly_engine.load_anomaly_thresholds()
        assert rules.repeated_delay_count == 5

    def test_companies_config_applies_to_datalake_client(self):
        """companies 설정이 법인 이름→코드 정규화에 반영된다."""
        from services import datalake_schedule_client

        save_config("companies", {"companies": [
            {"code": "NEWCO", "label": "NEWCO — 테스트",
             "lap_code": "S999"},
        ]})
        assert datalake_schedule_client.normalize_company_code(
            "NEWCO",
        ) == "S999"
        assert datalake_schedule_client.normalize_company_name(
            "S999",
        ) == "NEWCO"

    def test_companies_config_applies_to_marinesia_reader(self):
        """companies 설정이 AIS 허용 법인 집합에 반영된다."""
        from backend.app.services import marinesia_sharepoint_reader

        save_config("companies", {"companies": [
            {"code": "ONLYCO", "label": "ONLYCO", "lap_code": "S111"},
        ]})
        allowed = marinesia_sharepoint_reader._allowed_companies()
        assert allowed == {"ONLYCO"}

    def test_carrier_inference_custom_rules(self):
        """커스텀 carrier_inference 규칙이 추론에 반영된다."""
        from services import leadtime_report_service as svc

        save_config("carrier_inference", {
            "adria_arrival_ports": ["SIKOP"],
            "vessel_carrier_rules": [
                {"keyword": "HAPAG", "carrier_cd": "HLCU",
                 "carrier_nm": "Hapag-Lloyd"},
            ],
            "carrier_via_rules": [
                {"carrier_cd": "HLCU", "carrier_nm_contains": "HAPAG",
                 "via": "SUEZ"},
            ],
        })
        row = {
            "arvl": "SIKOP", "vessel_nm": "HAPAG LLOYD EXPRESS",
            "stopby": "", "stopby_nm": "",
            "carrier_cd": "", "carrier_nm": "",
        }
        result = svc.apply_europe_route_inference(row)
        assert result["carrier_cd"] == "HLCU"
        assert result["stopby"] == "SUEZ"

    def test_carrier_inference_fallback_when_config_missing(
        self, monkeypatch,
    ):
        """설정을 읽지 못하면 기존 하드코딩과 동일한 폴터 규칙을 쓴다."""
        from services import leadtime_report_service as svc

        monkeypatch.setattr(
            svc.config_store, "load_config", lambda *a, **k: None,
        )
        row = {
            "arvl": "SIKOP", "vessel_nm": "CMA CGM LIBERTY",
            "stopby": "", "stopby_nm": "",
            "carrier_cd": "", "carrier_nm": "",
        }
        result = svc.apply_europe_route_inference(row)
        assert result["carrier_cd"] == "CMAU"
        assert result["stopby"] == "SUEZ"
