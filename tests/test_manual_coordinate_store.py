"""backend/app/services/manual_coordinate_store.py 테스트.

MANUAL_COORDINATE_FILE 환경변수를 tmp_path로 주입해
upsert/get/list/delete, atomic write, 검증 룰을 확인한다.
"""
from __future__ import annotations

import json
import os

import pytest

from backend.app.services import manual_coordinate_store
from backend.app.services.manual_coordinate_store import (
    delete_manual_coordinate,
    get_manual_coordinate,
    list_manual_coordinates,
    manual_coordinate_health,
    normalize_company,
    normalize_location_code,
    resolve_manual_coordinate,
    upsert_manual_coordinate,
)


@pytest.fixture
def store_file(tmp_path, monkeypatch):
    path = tmp_path / "manual_coordinates.json"
    monkeypatch.setenv("MANUAL_COORDINATE_FILE", str(path))
    return path


class TestNormalize:
    def test_location_code_keeps_alnum_only(self):
        assert normalize_location_code(" kr-pus_01 ") == "KRPUS01"
        assert normalize_location_code("부산항") == ""
        assert normalize_location_code(None) == ""

    def test_company_uppercased(self):
        assert normalize_company(" skba ") == "SKBA"
        assert normalize_company(None) == ""


class TestUpsertAndGet:
    def test_upsert_creates_store_file(self, store_file):
        assert not store_file.exists()
        entry = upsert_manual_coordinate(
            location_code="krpus",
            latitude=35.1,
            longitude=129.03,
            location_name="부산",
            country_code="kr",
        )
        assert store_file.exists()
        assert entry["location_code"] == "KRPUS"
        assert entry["country_code"] == "KR"
        assert entry["latitude"] == 35.1
        assert entry["longitude"] == 129.03
        assert entry["scope"] == "GLOBAL"
        assert entry["source"] == "MANUAL"
        assert entry["created_at"]
        assert entry["updated_at"]

        fetched = get_manual_coordinate("KRPUS")
        assert fetched["location_name"] == "부산"

    def test_upsert_same_code_replaces_and_keeps_created_at(self, store_file):
        first = upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.1, longitude=129.03,
        )
        second = upsert_manual_coordinate(
            location_code="KRPUS", latitude=36.0, longitude=130.0,
        )
        items = list_manual_coordinates()
        assert len(items) == 1
        assert items[0]["latitude"] == 36.0
        assert second["created_at"] == first["created_at"]

    def test_list_sorted_by_code(self, store_file):
        upsert_manual_coordinate(
            location_code="EGSUZ", latitude=30.0, longitude=32.0,
        )
        upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.0, longitude=129.0,
        )
        codes = [item["location_code"] for item in list_manual_coordinates()]
        assert codes == ["EGSUZ", "KRPUS"]

    def test_get_unknown_returns_none(self, store_file):
        assert get_manual_coordinate("NOPE") is None
        assert get_manual_coordinate("") is None

    def test_latitude_validation(self, store_file):
        with pytest.raises(ValueError, match="위도"):
            upsert_manual_coordinate(
                location_code="KRPUS", latitude=91, longitude=0,
            )
        with pytest.raises(ValueError, match="위도"):
            upsert_manual_coordinate(
                location_code="KRPUS", latitude=-90.1, longitude=0,
            )

    def test_longitude_validation(self, store_file):
        with pytest.raises(ValueError, match="경도"):
            upsert_manual_coordinate(
                location_code="KRPUS", latitude=0, longitude=181,
            )

    def test_empty_code_rejected(self, store_file):
        with pytest.raises(ValueError, match="Location Code"):
            upsert_manual_coordinate(
                location_code="###", latitude=0, longitude=0,
            )


class TestDelete:
    def test_delete_existing(self, store_file):
        upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.1, longitude=129.03,
        )
        assert delete_manual_coordinate("krpus") is True
        assert list_manual_coordinates() == []

    def test_delete_missing_returns_false(self, store_file):
        assert delete_manual_coordinate("NOPE") is False


class TestResolve:
    def test_returns_lon_lat_order(self, store_file):
        upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.1, longitude=129.03,
        )
        # 지도 라이브러리 관례에 맞춰 (경도, 위도) 순서다.
        assert resolve_manual_coordinate("KRPUS") == (129.03, 35.1)

    def test_unknown_returns_none(self, store_file):
        assert resolve_manual_coordinate("NOPE") is None


class TestAtomicWrite:
    def test_no_temp_files_left(self, store_file):
        upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.1, longitude=129.03,
        )
        leftovers = list(store_file.parent.glob("*.tmp"))
        assert leftovers == []

    def test_written_document_is_valid_json(self, store_file):
        upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.1, longitude=129.03,
            location_name="부산항",
        )
        document = json.loads(store_file.read_text(encoding="utf-8"))
        assert document["version"] == 2
        assert document["scope"] == "GLOBAL"
        assert document["items"][0]["location_name"] == "부산항"


class TestCorruptedStore:
    def test_invalid_json_raises_runtime_error(self, store_file):
        store_file.write_text("{ broken json", encoding="utf-8")
        with pytest.raises(RuntimeError, match="읽지 못했습니다"):
            list_manual_coordinates()

    def test_non_dict_json_falls_back_to_empty(self, store_file):
        store_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert list_manual_coordinates() == []


class TestStorePathResolution:
    def test_username_placeholder_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERNAME", "testuser01")
        template = str(tmp_path / "{username}" / "manual_coordinates.json")
        monkeypatch.setenv("MANUAL_COORDINATE_FILE", template)
        path = manual_coordinate_store._store_path()
        assert "testuser01" in str(path)
        assert "{username}" not in str(path)

    def test_default_path_under_project_data(self, monkeypatch):
        monkeypatch.delenv("MANUAL_COORDINATE_FILE", raising=False)
        path = manual_coordinate_store._store_path()
        assert path.name == "manual_coordinates.json"
        assert path.parent.name == "data"


class TestHealth:
    def test_health_reports_item_count(self, store_file):
        upsert_manual_coordinate(
            location_code="KRPUS", latitude=35.1, longitude=129.03,
        )
        health = manual_coordinate_health()
        assert health["status"] == "ok"
        assert health["item_count"] == 1
        assert health["store_path"] == str(store_file)
